from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import pandas as pd

from .pipeline import run

ALLOWED_SCOPES = {
    "entities": "entity_search.parquet",
    "history": "company_year_enriched.parquet",
    "activities": "sii_activities_current.parquet",
    "addresses": "sii_addresses_history.parquet",
    "signals": "risk_signals.parquet",
}


def query_parquet(path: Path, text: str, filters: dict, limit: int) -> pd.DataFrame:
    con = duckdb.connect()
    safe_path = str(path).replace("'", "''")
    schema = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{safe_path}')").fetchdf()
    cols = schema["column_name"].tolist()
    clauses, params = [], []
    if text:
        text_cols = [c for c in ["rut", "legal_name", "legal_name_norm", "entity_id", "economic_sector", "economic_subsector", "main_activity", "activity_names", "activity_codes", "communes", "address_regions", "signal_types", "activity_name", "activity_code", "street", "commune", "region", "why_flagged"] if c in cols]
        if text_cols:
            clauses.append("(" + " OR ".join([f"lower(coalesce(cast({c} as varchar),'')) LIKE lower(?)" for c in text_cols]) + ")")
            params.extend([f"%{text}%"] * len(text_cols))
    exact_map = {
        "rut": "rut", "entity_id": "entity_id", "year": "commercial_year", "region": "region", "commune": "commune",
        "sales_band": "sales_band", "taxpayer_type": "taxpayer_type", "taxpayer_subtype": "taxpayer_subtype",
        "economic_sector": "economic_sector", "economic_subsector": "economic_subsector", "main_activity": "main_activity", "activity_code": "activity_code",
        "current_status": "current_status", "signal_type": "signal_type", "severity": "severity",
    }
    for key, col in exact_map.items():
        if key in filters and col in cols and filters[key] not in (None, ""):
            clauses.append(f"cast({col} as varchar) = ?")
            params.append(str(filters[key]))
    ranges = [("min_workers", "workers_numeric", ">="), ("max_workers", "workers_numeric", "<="), ("min_sales_rank", "sales_band_rank", ">="), ("max_sales_rank", "sales_band_rank", "<="), ("year_from", "commercial_year", ">="), ("year_to", "commercial_year", "<="), ("min_signal_count", "signal_count", ">="), ("min_address_count", "address_count", ">="), ("min_activity_count", "activity_count", ">=")]
    for key, col, op in ranges:
        if key in filters and col in cols and filters[key] not in (None, ""):
            clauses.append(f"{col} {op} ?")
            params.append(float(filters[key]))
    for key, col, op in [("start_date_from", "activity_start_date", ">="), ("start_date_to", "activity_start_date", "<="), ("termination_date_from", "termination_date", ">="), ("termination_date_to", "termination_date", "<=")]:
        if key in filters and col in cols and filters[key]:
            clauses.append(f"{col} {op} ?")
            params.append(str(filters[key]))
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    sql = f"SELECT * FROM read_parquet('{safe_path}') {where} LIMIT ?"
    return con.execute(sql, [*params, int(limit)]).fetchdf()


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
    if not args.reuse:
        run(Path("config/sources.yaml"), workdir, workdir / "metadata")
    parquet = workdir / "silver" / ALLOWED_SCOPES[args.scope]
    if not parquet.exists():
        raise FileNotFoundError(f"No se generó {parquet}; revise cobertura de la fuente")
    filters = json.loads(args.filters_json or "{}")
    result = query_parquet(parquet, args.text, filters, max(1, min(args.limit, 100000)))
    out = Path(args.result_dir)
    out.mkdir(parents=True, exist_ok=True)
    result.to_csv(out / "result.csv", index=False)
    result.to_json(out / "result.json", orient="records", force_ascii=False, indent=2)
    metadata = {"scope": args.scope, "text": args.text, "filters": filters, "limit": args.limit, "rows": len(result)}
    (out / "query_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False))


if __name__ == "__main__":
    main()
