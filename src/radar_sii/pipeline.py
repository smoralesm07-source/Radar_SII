from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from .analytics import build_analytics, quality_and_dashboard
from .extract import download, extract_primary_text, write_manifest
from .normalize import normalize_chunk, read_chunks
from .storage import ParquetAppender


def load_sources(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["sources"]


def process_source(source: dict, raw_dir: Path, extract_dir: Path, silver_dir: Path):
    snap = download(source["id"], source["url"], raw_dir)
    text_path = extract_primary_text(snap, extract_dir)
    parquet_path = silver_dir / f"{source['id']}.parquet"
    if parquet_path.exists():
        parquet_path.unlink()
    with ParquetAppender(parquet_path) as writer:
        for chunk in read_chunks(text_path, chunksize=int(source.get("chunksize", 100000))):
            writer.write(normalize_chunk(chunk, source["kind"], source["id"]))
    return parquet_path, snap


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
    core = {"sii_company_year", "sii_names_current", "sii_activities_current", "sii_addresses_history"}
    if core.issubset(set(processed)) or all((silver_dir / f"{sid}.parquet").exists() for sid in core):
        build_analytics(silver_dir)
        quality, dashboard = quality_and_dashboard(silver_dir, output_dir)
        coverage = {
            "sources_processed": sorted(processed),
            "company_year_min": 2020,
            "company_year_max": dashboard["kpis"]["latest_company_year"],
            "entities_searchable": dashboard["kpis"]["entities"],
            "signals": dashboard["kpis"]["signals"],
        }
    else:
        quality = {}
        coverage = {"sources_processed": sorted(processed), "analytics_built": False}
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
