from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import duckdb
import pandas as pd

from .pipeline import run
from .public_registry import apply_public_filters, enrich_public_entities, load_public_master, load_public_registry

ALLOWED_SCOPES = {
    "entities": "entity_search.parquet",
    "history": "company_year_enriched.parquet",
    "activities": "sii_activities_current.parquet",
    "addresses": "sii_addresses_history.parquet",
    "ownership": "sii_ownership_current.parquet",
    "signals": "risk_signals.parquet",
    "document_authorizations": "sii_document_authorizations.parquet",
    "public_entities": "__PUBLIC_REGISTRY__",
}


def query_parquet(
    path: Path,
    text: str,
    filters: dict,
    limit: int,
    allowed_entity_ids: list[str] | None = None,
) -> pd.DataFrame:
    con = duckdb.connect()
    safe_path = str(path).replace("'", "''")
    schema = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{safe_path}')").fetchdf()
    cols = schema["column_name"].tolist()
    clauses, params = [], []
    if allowed_entity_ids is not None:
        if "entity_id" not in cols:
            return pd.DataFrame(columns=cols)
        if not allowed_entity_ids:
            return pd.DataFrame(columns=cols)
        placeholders = ",".join(["?"] * len(allowed_entity_ids))
        clauses.append(f"cast(entity_id as varchar) IN ({placeholders})")
        params.extend(allowed_entity_ids)
    if text:
        candidates = [
            "rut", "legal_name", "legal_name_norm", "entity_id", "economic_sector", "economic_subsector",
            "main_activity", "activity_names", "activity_codes", "communes", "address_regions", "signal_types",
            "activity_name", "activity_code", "street", "commune", "region", "why_flagged", "society_type",
            "society_subtype", "partner_rut", "partner_entity_id", "partner_id_type", "partner_group_id",
            "document_type_code", "document_type_name", "document_number", "authorization_status", "source_system",
        ]
        text_cols = [c for c in candidates if c in cols]
        if text_cols:
            clauses.append("(" + " OR ".join([f"lower(coalesce(cast({c} as varchar),'')) LIKE lower(?)" for c in text_cols]) + ")")
            params.extend([f"%{text}%"] * len(text_cols))
    exact_map = {
        "rut": "rut", "entity_id": "entity_id", "year": "commercial_year", "region": "region", "commune": "commune",
        "sales_band": "sales_band", "sales_band_code": "sales_band_code", "taxpayer_type": "taxpayer_type",
        "taxpayer_subtype": "taxpayer_subtype", "taxpayer_subtype_code": "taxpayer_subtype_code",
        "economic_sector": "economic_sector", "economic_subsector": "economic_subsector", "main_activity": "main_activity",
        "activity_code": "activity_code", "current_status": "current_status", "signal_type": "signal_type", "severity": "severity",
        "partner_rut": "partner_rut", "partner_entity_id": "partner_entity_id", "partner_id_type": "partner_id_type",
        "society_type": "society_type", "society_subtype": "society_subtype",
        "document_type_code": "document_type_code", "authorization_status": "authorization_status",
        "observation_kind": "observation_kind", "source_system": "source_system",
    }
    for key, col in exact_map.items():
        if key in filters and col in cols and filters[key] not in (None, ""):
            clauses.append(f"cast({col} as varchar) = ?")
            params.append(str(filters[key]))
    ranges = [
        ("min_workers", "workers_numeric", ">="), ("max_workers", "workers_numeric", "<="),
        ("min_sales_rank", "sales_band_rank", ">="), ("max_sales_rank", "sales_band_rank", "<="),
        ("year_from", "commercial_year", ">="), ("year_to", "commercial_year", "<="),
        ("min_signal_count", "signal_count", ">="), ("min_address_count", "address_count", ">="),
        ("min_activity_count", "activity_count", ">="), ("min_ownership_percent", "ownership_percent", ">="),
        ("max_ownership_percent", "ownership_percent", "<="), ("min_ownership_edges", "ownership_edge_count", ">="),
        ("min_societies_as_partner", "societies_as_partner_count", ">="),
    ]
    for key, col, op in ranges:
        if key in filters and col in cols and filters[key] not in (None, ""):
            clauses.append(f"{col} {op} ?")
            params.append(float(filters[key]))
    date_ranges = [
        ("start_date_from", "activity_start_date", ">="), ("start_date_to", "activity_start_date", "<="),
        ("termination_date_from", "termination_date", ">="), ("termination_date_to", "termination_date", "<="),
        ("activity_date_from", "activity_registration_date", ">="), ("activity_date_to", "activity_registration_date", "<="),
        ("address_date_from", "address_date", ">="), ("address_date_to", "address_date", "<="),
        ("authorization_date_from", "authorization_date", ">="), ("authorization_date_to", "authorization_date", "<="),
        ("document_date_from", "document_date", ">="), ("document_date_to", "document_date", "<="),
    ]
    for key, col, op in date_ranges:
        if key in filters and col in cols and filters[key]:
            clauses.append(f"try_cast({col} AS DATE) {op} try_cast(? AS DATE)")
            params.append(str(filters[key]))
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    sql = f"SELECT * FROM read_parquet('{safe_path}') {where} LIMIT ?"
    return con.execute(sql, [*params, int(limit)]).fetchdf()


def _as_bool(series: pd.Series) -> pd.Series:
    return series.fillna("false").astype(str).str.lower().eq("true")


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "si", "sí", "yes"}


def _preselect_public_entity_ids(filters: dict) -> list[str] | None:
    wants_public = filters.get("is_public_entity") not in (None, "") and _truthy(filters.get("is_public_entity"))
    wants_strict = filters.get("is_public_service_strict") not in (None, "") and _truthy(filters.get("is_public_service_strict"))
    wants_type = filters.get("public_entity_type") not in (None, "")
    if not (wants_public or wants_strict or wants_type):
        return None
    registry = load_public_registry(Path("config/public_entities_registry.csv"))
    if registry.empty:
        return []
    subset = apply_public_filters(registry, {
        k: v for k, v in filters.items()
        if k in {"is_public_entity", "is_public_service_strict", "public_entity_type"}
    })
    return sorted({str(x) for x in subset["entity_id"] if str(x)})


def query_public_registry(text: str, filters: dict, limit: int) -> pd.DataFrame:
    df = load_public_master(Path("config/public_entities_registry.csv"))
    if df.empty:
        return df
    if text:
        mask = pd.Series(False, index=df.index)
        for col in ["official_name", "public_entity_type", "rut", "entity_id", "source_code"]:
            if col in df.columns:
                mask |= df[col].astype(str).str.contains(text, case=False, regex=False)
        df = df[mask]
    if filters.get("rut") not in (None, "") and "rut" in df.columns:
        df = df[df["rut"].astype(str) == str(filters["rut"])]
    if filters.get("entity_id") not in (None, "") and "entity_id" in df.columns:
        df = df[df["entity_id"].astype(str) == str(filters["entity_id"])]
    if filters.get("public_entity_type") not in (None, "") and "public_entity_type" in df.columns:
        df = df[df["public_entity_type"].astype(str).str.contains(str(filters["public_entity_type"]), case=False, regex=False)]
    if filters.get("is_public_service_strict") not in (None, "") and "is_public_service_strict" in df.columns:
        expected = _truthy(filters["is_public_service_strict"])
        df = df[_as_bool(df["is_public_service_strict"]) == expected]
    return df.head(limit).copy()


def _copy_lineage(metadata_dir: Path, out: Path) -> dict:
    lineage: dict = {}
    for name in ("snapshot_manifest.json", "source_catalog.json", "coverage.json", "quality.json"):
        src = metadata_dir / name
        if src.exists():
            shutil.copy2(src, out / name)
            try:
                lineage[name.removesuffix(".json")] = json.loads(src.read_text(encoding="utf-8"))
            except Exception:
                lineage[name.removesuffix(".json")] = {"copied": True}
    public_summary = Path("docs/data/public_entities_summary.json")
    if public_summary.exists():
        shutil.copy2(public_summary, out / public_summary.name)
        try:
            lineage["public_entities_summary"] = json.loads(public_summary.read_text(encoding="utf-8"))
        except Exception:
            lineage["public_entities_summary"] = {"copied": True}
    return lineage


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--scope", choices=sorted(ALLOWED_SCOPES), default="entities")
    p.add_argument("--text", default="")
    p.add_argument("--filters-json", default="{}")
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--workdir", default=".radar_sii")
    p.add_argument("--result-dir", default="query_result")
    p.add_argument("--reuse", action="store_true", help="Usar parquet existentes en workdir/silver")
    args = p.parse_args()
    workdir = Path(args.workdir)
    metadata_dir = workdir / "metadata"
    filters = json.loads(args.filters_json or "{}")
    safe_limit = max(1, min(args.limit, 100000))

    if args.scope == "public_entities":
        result = query_public_registry(args.text, filters, safe_limit)
    else:
        if not args.reuse:
            run(Path("config/sources.yaml"), workdir, metadata_dir)
        parquet = workdir / "silver" / ALLOWED_SCOPES[args.scope]
        if not parquet.exists():
            raise FileNotFoundError(f"No se generó {parquet}; revise cobertura de la fuente")
        base_filters = {k: v for k, v in filters.items() if k not in {"is_public_entity", "is_public_service_strict", "public_entity_type"}}
        allowed_entity_ids = _preselect_public_entity_ids(filters)
        result = query_parquet(parquet, args.text, base_filters, safe_limit, allowed_entity_ids=allowed_entity_ids)
        result = enrich_public_entities(result)
        result = apply_public_filters(result, filters).head(safe_limit)

    out = Path(args.result_dir)
    out.mkdir(parents=True, exist_ok=True)
    result.to_csv(out / "result.csv", index=False)
    result.to_json(out / "result.json", orient="records", force_ascii=False, indent=2)
    lineage = _copy_lineage(metadata_dir, out)
    metadata = {
        "scope": args.scope,
        "text": args.text,
        "filters": filters,
        "limit": args.limit,
        "rows": len(result),
        "public_registry_enabled": Path("config/public_entities_registry.csv").exists(),
        "source_snapshot_count": len(lineage.get("snapshot_manifest", [])) if isinstance(lineage.get("snapshot_manifest"), list) else None,
        "history_complete": lineage.get("coverage", {}).get("history_complete") if isinstance(lineage.get("coverage"), dict) else None,
        "company_years": lineage.get("coverage", {}).get("company_years") if isinstance(lineage.get("coverage"), dict) else None,
        "public_entities": lineage.get("public_entities_summary", {}).get("public_entities_chilecompra") if isinstance(lineage.get("public_entities_summary"), dict) else None,
    }
    (out / "query_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False))


if __name__ == "__main__":
    main()
