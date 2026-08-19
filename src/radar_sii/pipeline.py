from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .analytics import build_analytics, quality_and_dashboard
from .company_year import canonicalize_company_year
from .extract import download, extract_source_files, write_manifest
from .normalize import normalize_chunk, read_chunks
from .public_analysis import enrich_analytical_outputs, inject_public_metrics
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
    with ParquetAppender(parquet_path) as writer:
        total_rows = 0
        member_rows: dict[str, int] = {}
        for text_path in text_paths:
            member_total = 0
            print(f"[Radar SII] normalizando {source_id}/{text_path.name}", flush=True)
            for chunk in read_chunks(text_path, chunksize=int(source.get("chunksize", 100000))):
                normalized = normalize_chunk(chunk, source["kind"], source_id)
                writer.write(normalized)
                member_total += len(normalized)
                total_rows += len(normalized)
            member_rows[text_path.name] = member_total
            print(f"[Radar SII] {text_path.name}: {member_total:,} filas", flush=True)
            text_path.unlink(missing_ok=True)
    snap.normalized_rows = total_rows
    snap.member_rows = member_rows
    print(f"[Radar SII] {source_id}: {total_rows:,} filas normalizadas", flush=True)
    return parquet_path, snap


def _source_by_id(sources: list[dict], source_id: str) -> dict:
    return next((s for s in sources if s["id"] == source_id), {})


def _load_company_year_quality(silver_dir: Path) -> dict:
    path = silver_dir / "company_year_source_quality.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _quarantine_future_start_years(dashboard: dict, quality: dict) -> None:
    """No elimina evidencia fuente: solo evita publicar años futuros imposibles en agregados analíticos."""
    current_year = datetime.now(timezone.utc).year
    start_years = dashboard.get("start_years", {}) or {}
    valid: dict[str, int] = {}
    future: dict[str, int] = {}
    for year, count in start_years.items():
        try:
            y = int(year)
        except (TypeError, ValueError):
            continue
        target = future if y > current_year else valid
        target[str(y)] = int(count)
    dashboard["start_years"] = valid
    quality.setdefault("date_anomalies", {})["future_activity_start_years"] = future
    quality["date_anomalies"]["future_activity_start_rows"] = int(sum(future.values()))


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

    company_year_quality: dict = {}
    if "sii_company_year" in processed:
        print("[Radar SII] validando y canonicalizando hechos empresa-año", flush=True)
        company_year_quality = canonicalize_company_year(silver_dir)
    else:
        company_year_quality = _load_company_year_quality(silver_dir)

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
        print("[Radar SII] incorporando contexto de entidades públicas", flush=True)
        public_metrics = enrich_analytical_outputs(silver_dir)
        quality, dashboard = quality_and_dashboard(silver_dir, output_dir)
        _quarantine_future_start_years(dashboard, quality)
        if company_year_quality:
            quality["company_year_source"] = company_year_quality
        (output_dir / "quality.json").write_text(
            json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (output_dir / "dashboard.json").write_text(
            json.dumps(dashboard, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        inject_public_metrics(output_dir, public_metrics)
        expected_years = [int(x) for x in _source_by_id(sources, "sii_company_year").get("expected_years", [])]
        observed_years = [int(x) for x in quality.get("company_year", {}).get("years", [])]
        history_complete = not expected_years or observed_years == expected_years
        if not history_complete:
            raise RuntimeError(f"Cobertura histórica SII incompleta: esperados={expected_years}, observados={observed_years}")
        coverage = {
            "sources_processed": sorted(processed),
            "source_rows": {s.source_id: s.normalized_rows for s in snapshots},
            "company_year_source_rows": company_year_quality.get("source_rows"),
            "company_year_canonical_rows": company_year_quality.get("canonical_rows"),
            "company_year_source_duplicate_rows": company_year_quality.get("source_duplicate_entity_year_rows"),
            "company_year_termination_conflict_groups": company_year_quality.get("termination_date_conflict_groups"),
            "company_year_stable_conflict_groups": company_year_quality.get("stable_payload_conflict_groups"),
            "company_year_min": min(observed_years) if observed_years else None,
            "company_year_max": max(observed_years) if observed_years else None,
            "company_years": observed_years,
            "history_complete": history_complete,
            "entities_searchable": dashboard["kpis"]["entities"],
            "signals": dashboard["kpis"]["signals"],
            "ownership_edges": dashboard["kpis"].get("ownership_edges", 0),
            "public_entity_context": public_metrics,
        }
    else:
        quality = {"company_year_source": company_year_quality} if company_year_quality else {}
        if quality:
            (output_dir / "quality.json").write_text(
                json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        coverage = {
            "sources_processed": sorted(processed),
            "source_rows": {s.source_id: s.normalized_rows for s in snapshots},
            "company_year_source_rows": company_year_quality.get("source_rows"),
            "company_year_canonical_rows": company_year_quality.get("canonical_rows"),
            "company_year_source_duplicate_rows": company_year_quality.get("source_duplicate_entity_year_rows"),
            "company_year_termination_conflict_groups": company_year_quality.get("termination_date_conflict_groups"),
            "company_year_stable_conflict_groups": company_year_quality.get("stable_payload_conflict_groups"),
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
