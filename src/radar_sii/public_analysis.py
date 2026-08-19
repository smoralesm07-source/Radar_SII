from __future__ import annotations

import json
from pathlib import Path

import duckdb


def _q(path: Path) -> str:
    return str(path).replace("'", "''")


def _public_context_sql(registry_path: Path) -> str:
    if not registry_path.exists() or registry_path.stat().st_size == 0:
        return """
        SELECT CAST(NULL AS VARCHAR) entity_id,
               FALSE is_public_entity,
               FALSE is_public_service_strict,
               CAST('' AS VARCHAR) public_entity_type,
               CAST('' AS VARCHAR) public_entity_name,
               CAST('' AS VARCHAR) public_entity_source_system,
               CAST('' AS VARCHAR) public_entity_source_code
        WHERE FALSE
        """
    reg = _q(registry_path)
    return f"""
    WITH p0 AS (
      SELECT * FROM read_csv_auto('{reg}', delim=';', header=true, all_varchar=true)
      WHERE coalesce(entity_id,'') <> ''
    )
    SELECT entity_id,
           TRUE AS is_public_entity,
           bool_or(lower(coalesce(is_public_service_strict,'false'))='true') AS is_public_service_strict,
           string_agg(DISTINCT nullif(public_entity_type,''), ' | ') AS public_entity_type,
           string_agg(DISTINCT nullif(official_name,''), ' | ') AS public_entity_name,
           string_agg(DISTINCT nullif(source_system,''), ' | ') AS public_entity_source_system,
           string_agg(DISTINCT nullif(source_code,''), ' | ') AS public_entity_source_code
    FROM p0
    GROUP BY entity_id
    """


def _rewrite_parquet(con: duckdb.DuckDBPyConnection, path: Path, sql: str) -> None:
    temp = path.with_name(path.stem + "_public_enriched.parquet")
    if temp.exists():
        temp.unlink()
    con.execute(f"COPY ({sql}) TO '{_q(temp)}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    temp.replace(path)


def enrich_analytical_outputs(
    silver_dir: Path,
    registry_path: Path = Path("config/public_entities_registry.csv"),
) -> dict:
    """Adds public-sector context without changing the original analytical signal semantics."""
    entity_path = silver_dir / "entity_search.parquet"
    signal_path = silver_dir / "risk_signals.parquet"
    if not entity_path.exists() or not signal_path.exists():
        return {"enabled": False, "reason": "analytical_outputs_missing"}

    con = duckdb.connect()
    public_sql = _public_context_sql(registry_path)
    con.execute(f"CREATE OR REPLACE TEMP VIEW public_ctx AS {public_sql}")

    entity = _q(entity_path)
    entity_cols = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{entity}')").fetchall()}
    if "is_public_entity" not in entity_cols:
        entity_sql = f"""
        SELECT e.*,
               coalesce(p.is_public_entity,FALSE) AS is_public_entity,
               coalesce(p.is_public_service_strict,FALSE) AS is_public_service_strict,
               coalesce(p.public_entity_type,'') AS public_entity_type,
               coalesce(p.public_entity_name,'') AS public_entity_name,
               coalesce(p.public_entity_source_system,'') AS public_entity_source_system,
               coalesce(p.public_entity_source_code,'') AS public_entity_source_code,
               CASE WHEN coalesce(p.is_public_entity,FALSE)
                    THEN 'PUBLIC_ENTITY_CONTEXT' ELSE 'PRIVATE_OR_OTHER_ENTITY' END AS analysis_population,
               NOT coalesce(p.is_public_entity,FALSE) AS business_ranking_eligible
        FROM read_parquet('{entity}') e
        LEFT JOIN public_ctx p USING(entity_id)
        """
        _rewrite_parquet(con, entity_path, entity_sql)

    signal = _q(signal_path)
    signal_cols = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{signal}')").fetchall()}
    if "is_public_entity" not in signal_cols:
        signal_sql = f"""
        SELECT s.*,
               coalesce(p.is_public_entity,FALSE) AS is_public_entity,
               coalesce(p.is_public_service_strict,FALSE) AS is_public_service_strict,
               coalesce(p.public_entity_type,'') AS public_entity_type,
               coalesce(p.public_entity_name,'') AS public_entity_name,
               CASE WHEN coalesce(p.is_public_entity,FALSE)
                    THEN 'PUBLIC_ENTITY_CONTEXT' ELSE 'PRIVATE_OR_OTHER_ENTITY' END AS analysis_population,
               NOT coalesce(p.is_public_entity,FALSE) AS business_ranking_eligible,
               CASE WHEN coalesce(p.is_public_entity,FALSE)
                    THEN 'CONTEXT_ONLY_PUBLIC_ENTITY'
                    ELSE 'STANDARD_BUSINESS_SIGNAL' END AS signal_applicability
        FROM read_parquet('{signal}') s
        LEFT JOIN public_ctx p USING(entity_id)
        """
        _rewrite_parquet(con, signal_path, signal_sql)

    entity = _q(entity_path)
    signal = _q(signal_path)
    counts = con.execute(
        f"SELECT count(*) FILTER (WHERE is_public_entity), "
        f"count(*) FILTER (WHERE is_public_service_strict) FROM read_parquet('{entity}')"
    ).fetchone()
    signal_counts = con.execute(
        f"SELECT count(*), count(*) FILTER (WHERE is_public_entity) FROM read_parquet('{signal}')"
    ).fetchone()
    return {
        "enabled": True,
        "registry_exists": registry_path.exists(),
        "public_entities_matched_in_entity_search": int(counts[0] or 0),
        "strict_public_services_matched_in_entity_search": int(counts[1] or 0),
        "signals_total": int(signal_counts[0] or 0),
        "signals_public_entity_context": int(signal_counts[1] or 0),
    }


def inject_public_metrics(output_dir: Path, metrics: dict) -> None:
    """Adds non-adverse public-context KPIs after standard quality/dashboard generation."""
    if not metrics.get("enabled"):
        return
    quality_path = output_dir / "quality.json"
    dashboard_path = output_dir / "dashboard.json"

    if quality_path.exists():
        quality = json.loads(quality_path.read_text(encoding="utf-8"))
        quality["public_entity_context"] = {
            **metrics,
            "semantics": "PUBLIC_STATUS_IS_CONTEXT_NOT_ADVERSE_SIGNAL",
            "ranking_policy": "PUBLIC_ENTITIES_EXCLUDED_FROM_STANDARD_BUSINESS_RANKING_BY_DEFAULT",
        }
        quality_path.write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")

    if dashboard_path.exists():
        dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
        kpis = dashboard.setdefault("kpis", {})
        kpis["public_entities_matched"] = metrics["public_entities_matched_in_entity_search"]
        kpis["public_services_strict_matched"] = metrics["strict_public_services_matched_in_entity_search"]
        kpis["signals_public_entity_context"] = metrics["signals_public_entity_context"]
        dashboard["public_entity_analysis_policy"] = {
            "business_ranking_eligible_default": False,
            "interpretation": "La condición de entidad pública es contexto institucional y no señal adversa.",
        }
        dashboard_path.write_text(json.dumps(dashboard, ensure_ascii=False, indent=2), encoding="utf-8")
