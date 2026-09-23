from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import duckdb

SCHEMA = "RADAR_SII_TAX_HISTORY_WEB_V1"
RUT_RE = re.compile(r"^[0-9]{7,9}[0-9K]$")


def flush(prefix: str | None, entities: dict[str, list[list[int | None]]], out_dir: Path) -> tuple[int, int]:
    if not prefix or not entities:
        return 0, 0
    payload = {
        "schema": SCHEMA,
        "prefix": prefix,
        "entities": entities,
    }
    target = out_dir / f"{prefix}.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return len(entities), sum(len(rows) for rows in entities.values())


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit("usage: build_tax_history_pages.py INPUT.parquet OUTPUT_DIR [SOURCE_MANIFEST.json]")

    src = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    manifest_path = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    if not src.exists():
        raise SystemExit(f"missing parquet: {src}")

    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.json"):
        old.unlink()

    con = duckdb.connect()
    escaped = str(src).replace("'", "''")
    cursor = con.execute(
        f"""
        select
          regexp_replace(upper(substr(entity_id, 9)), '[^0-9K]', '', 'g') as rut_compact,
          cast(commercial_year as integer) as commercial_year,
          cast(sales_band_rank as integer) as sales_band_rank,
          cast(workers_numeric as integer) as workers_numeric
        from read_parquet('{escaped}')
        where entity_id is not null
          and upper(entity_id) like 'ENT-RUT-%'
          and commercial_year is not null
        order by substr(rut_compact, 1, 3), rut_compact, commercial_year
        """
    )

    current_prefix: str | None = None
    entities: dict[str, list[list[int | None]]] = {}
    entity_count = 0
    row_count = 0
    shard_count = 0
    skipped = 0

    while True:
        batch = cursor.fetchmany(50_000)
        if not batch:
            break
        for rut, year, rank, workers in batch:
            rut = str(rut or "").upper()
            if not RUT_RE.fullmatch(rut):
                skipped += 1
                continue
            prefix = rut[:3]
            if current_prefix is None:
                current_prefix = prefix
            elif prefix != current_prefix:
                e, r = flush(current_prefix, entities, out_dir)
                entity_count += e
                row_count += r
                shard_count += 1
                entities = {}
                current_prefix = prefix
            entities.setdefault(rut, []).append([
                int(year),
                None if rank is None else int(rank),
                None if workers is None else int(workers),
            ])

    e, r = flush(current_prefix, entities, out_dir)
    if e:
        entity_count += e
        row_count += r
        shard_count += 1

    source_manifest = {}
    if manifest_path and manifest_path.exists():
        source_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    web_manifest = {
        "schema": SCHEMA,
        "source_schema": source_manifest.get("schema"),
        "source_run_id": source_manifest.get("source_run_id"),
        "source_sha256": source_manifest.get("sha256"),
        "source_rows": source_manifest.get("rows"),
        "source_entities": source_manifest.get("entities"),
        "min_year": source_manifest.get("min_year"),
        "max_year": source_manifest.get("max_year"),
        "rows": row_count,
        "entities": entity_count,
        "shards": shard_count,
        "skipped_rows": skipped,
        "semantics": "SII annual sales-band rank and declared workers; sales band 1 means no sales information, not zero sales.",
    }
    (out_dir / "manifest.json").write_text(json.dumps(web_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    if source_manifest.get("rows") is not None and row_count < int(source_manifest["rows"]) * 0.99:
        raise RuntimeError(f"web history coverage too low: {row_count} of {source_manifest['rows']}")

    # Regression guard for the Entity 360 case that exposed the coverage gap.
    target = "761180673"
    target_file = out_dir / f"{target[:3]}.json"
    if target_file.exists():
        target_payload = json.loads(target_file.read_text(encoding="utf-8"))
        years = [row[0] for row in target_payload.get("entities", {}).get(target, [])]
        if len(years) < 2:
            raise RuntimeError("76118067-3 does not expose historical years in the web layer")
        print(f"76118067-3 historical years: {years}")
    else:
        raise RuntimeError("missing shard for 76118067-3")

    print(json.dumps(web_manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
