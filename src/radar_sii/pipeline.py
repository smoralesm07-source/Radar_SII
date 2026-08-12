from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from .analytics import build_analytics, quality_and_dashboard
from .extract import download, extract_source_files, write_manifest
from .normalize import normalize_chunk, read_chunks
from .storage import ParquetAppender


def load_sources(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["sources"]


def process_source(source: dict, raw_dir: Path, extract_dir: Path, silver_dir: Path):
    source_id = source["id"]
    print(f"[Radar SII] descargando {source_id}", flush=True)
    snap = download(source_id, source["url"], raw_dir, source_meta=source)
    text_paths = extract_source_files(snap, extract_dir, member_globs=source.get("member_globs"))
    parquet_path = silver_dir / f"{source_id}.parquet"
    if parquet_path.exists():
        parquet_path.unlink()
    total_rows = 0
    member_rows: dict[str, int] = {}
    with ParquetAppender(parquet_path) as writer:
        for text_path in text_paths:
            member_total = 0
            print(f"[Radar SII] normalizando {source_id}/{text_path.name}", flush=True)
            for chunk in read_chunks(text_path, chunksize=int(source.get("chunksize", 100000))):
                normalized = normalize_chunk(chunk, source["kind"], source_id)
                writer.write(normalized)
                rows = len(normalized)
                member_total += rows
                total_rows += rows
            member_rows[text_path.name] = member_total
            print(f"[Radar SII] {text_path.name}: {member_total:,} filas", flush=True)
            text_path.unlink(missing_ok=True)
    snap.normalized_rows = total_rows
    snap.member_rows = member_rows
    print(f"[Radar SII] {source_id}: {total_rows:,} filas normalizadas", flush=True)
    return parquet_path, snap


def _source_by_id(sources: list[dict], source_id: str) -> dict:
    return next((s for s in sources if s["id"] == source_id), {})


def run(sources_path: Path, workdir: Path, output_dir: Path, only: set[str] | None = None) -> dict:
    raw_dir, extract_dir, silver_dir = workdir / "raw", workdir / "extracted", workdir / "silver"
    for p in (raw_dir, extract_dir, silver_dir, output_dir):
        p.mkdir(parents=True, exist_ok=True)
    sources = load_sources(sources_path)
    snapshots = []
    processed = []
    for source in sources:
        if only and source["id"] not in only:
            continue
        _, snap = process_source(source, raw_dir, extract_dir, silver_dir)
        snapshots.append(snap)
        processed.append(source["id"])
    write_manifest(snapshots, output_dir / "snapshot_manifest.json")
    (output_dir / "source_catalog.json").write_text(json.dumps(sources, ensure_ascii=False, indent=2), encoding="utf-8")

    core = {
        "sii_company_year",
        "sii_names_current",
        "sii_activities_current",
        "sii_addresses_history",
        "sii_ownership_current",
    }
    if core.issubset(set(processed)) or all((silver_dir / f"{sid}.parquet").exists() for sid in core):
        print("[Radar SII] construyendo analítica y señales", flush=True)
        build_analytics(silver_dir)
        quality, dashboard = quality_and_dashboard(silver_dir, output_dir)
        expected_years = [int(x) for x in _source_by_id(sources, "sii_company_year").get("expected_years", [])]
        observed_years = [int(x) for x in quality.get("company_year", {}).get("years", [])]
        history_complete = not expected_years or observed_years == expected_years
        if not history_complete:
            raise RuntimeError(f"Cobertura histórica SII incompleta: esperados={expected_years}, observados={observed_years}")
        coverage = {
            "sources_processed": sorted(processed),
            "source_rows": {s.source_id: s.normalized_rows for s in snapshots},
            "company_year_min": min(observed_years) if observed_years else None,
            "company_year_max": max(observed_years) if observed_years else None,
            "company_years": observed_years,
            "history_complete": history_complete,
            "entities_searchable": dashboard["kpis"]["entities"],
            "signals": dashboard["kpis"]["signals"],
            "ownership_edges": dashboard["kpis"].get("ownership_edges", 0),
        }
    else:
        quality = {}
        coverage = {
            "sources_processed": sorted(processed),
            "source_rows": {s.source_id: s.normalized_rows for s in snapshots},
            "analytics_built": False,
        }
    (output_dir / "coverage.json").write_text(json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"silver_dir": str(silver_dir), "coverage": coverage, "quality": quality}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--sources", default="config/sources.yaml")
    p.add_argument("--workdir", default=".radar_sii")
    p.add_argument("--output", default="docs/data")
    p.add_argument("--only", default="", help="IDs separados por coma")
    args = p.parse_args()
    only = {x.strip() for x in args.only.split(",") if x.strip()} or None
    result = run(Path(args.sources), Path(args.workdir), Path(args.output), only=only)
    print(json.dumps(result["coverage"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
