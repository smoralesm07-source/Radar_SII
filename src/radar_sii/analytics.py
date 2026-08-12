from __future__ import annotations

import json
from pathlib import Path

import duckdb


def _q(path: Path) -> str:
    return str(path).replace("'", "''")


def _copy(con: duckdb.DuckDBPyConnection, sql: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    con.execute(f"COPY ({sql}) TO '{_q(path)}' (FORMAT PARQUET, COMPRESSION ZSTD)")


def _sales_rank_sql(col: str = "sales_band") -> str:
    u = f"upper(coalesce({col},''))"
    return f"""
    CASE
      WHEN {u} LIKE '%MAS DE 1.000.000%' OR {u} LIKE '%1.000.000,01%' THEN 12
      WHEN {u} LIKE '%600.000,01%' THEN 11
      WHEN {u} LIKE '%200.000,01%' THEN 10
      WHEN {u} LIKE '%100.000,01%' THEN 9
      WHEN {u} LIKE '%50.000,01%' THEN 8
      WHEN {u} LIKE '%25.000,01%' THEN 7
      WHEN {u} LIKE '%10.000,01%' THEN 6
      WHEN {u} LIKE '%5.000,01%' THEN 5
      WHEN {u} LIKE '%2.400,01%' THEN 4
      WHEN {u} LIKE '%600,01%' THEN 3
      WHEN {u} LIKE '%200,01%' THEN 2
      WHEN {u} LIKE '%0,01%' THEN 1
      WHEN {u} LIKE '%SIN INFORMACION%' OR {u} LIKE '%SIN INFORMACIÓN%' OR {u} LIKE '%SIN VENTAS%' THEN 0
      ELSE NULL
    END
    """


def build_analytics(silver_dir: Path) -> dict:
    con = duckdb.connect()
    cy_src = silver_dir / "sii_company_year.parquet"
    names_src = silver_dir / "sii_names_current.parquet"
    acts_src = silver_dir / "sii_activities_current.parquet"
    addr_src = silver_dir / "sii_addresses_history.parquet"
    required = [cy_src, names_src, acts_src, addr_src]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Faltan fuentes normalizadas: {missing}")

    cy_enriched = silver_dir / "company_year_enriched.parquet"
    sales_rank = _sales_rank_sql("sales_band")
    cy_sql = f"""
    WITH base AS (
      SELECT *,
             {sales_rank} AS sales_band_rank,
             try_cast(workers AS BIGINT) AS workers_numeric,
             commercial_year - year(try_cast(nullif(activity_start_date,'') AS DATE)) AS entity_age_years
      FROM read_parquet('{_q(cy_src)}')
    )
    SELECT *,
           lag(sales_band_rank) OVER (PARTITION BY entity_id ORDER BY commercial_year, record_id) AS prior_sales_band_rank,
           sales_band_rank - lag(sales_band_rank) OVER (PARTITION BY entity_id ORDER BY commercial_year, record_id) AS sales_band_delta,
           lag(region) OVER (PARTITION BY entity_id ORDER BY commercial_year, record_id) AS prior_region,
           CASE WHEN lag(region) OVER (PARTITION BY entity_id ORDER BY commercial_year, record_id) IS NOT NULL
                  AND coalesce(region,'') <> coalesce(lag(region) OVER (PARTITION BY entity_id ORDER BY commercial_year, record_id),'')
                THEN TRUE ELSE FALSE END AS region_changed
    FROM base
    """
    _copy(con, cy_sql, cy_enriched)

    signals_path = silver_dir / "risk_signals.parquet"
    sig_sql = f"""
    WITH cy AS (SELECT * FROM read_parquet('{_q(cy_enriched)}')),
    cy_signals AS (
      SELECT entity_id, 'SALES_BAND_JUMP' signal_type, cast(commercial_year AS VARCHAR) period,
             'MEDIUM' severity, 50 severity_score, 'HIGH' confidence,
             'El tramo de ventas aumentó al menos 3 niveles respecto del año anterior publicado.' why_flagged,
             'Comparar con pares del mismo rubro y revisar continuidad de actividad, giros y contrapartes en otros radares.' recommended_checks,
             record_id source_record_id
      FROM cy WHERE sales_band_delta >= 3
      UNION ALL
      SELECT entity_id, 'HIGH_SALES_LOW_WORKFORCE', cast(commercial_year AS VARCHAR),
             'MEDIUM', 50, 'MEDIUM',
             'Tramo de ventas alto con 2 o menos trabajadores dependientes informados.',
             'Contextualizar por industria; revisar evolución de trabajadores, actividades y domicilios.', record_id
      FROM cy WHERE sales_band_rank >= 9 AND workers_numeric <= 2
      UNION ALL
      SELECT entity_id, 'RECENT_START_HIGH_SALES', cast(commercial_year AS VARCHAR),
             'MEDIUM', 50, 'MEDIUM',
             'Empresa con hasta 2 años desde el inicio publicado y tramo de ventas alto.',
             'Validar historia societaria y cruzar con contratación pública/CGR cuando corresponda.', record_id
      FROM cy WHERE sales_band_rank >= 9 AND entity_age_years BETWEEN 0 AND 2
      UNION ALL
      SELECT entity_id, 'HIGH_SALES_NEGATIVE_EQUITY', cast(commercial_year AS VARCHAR),
             'MEDIUM', 50, 'MEDIUM',
             'Tramo de ventas alto coexistiendo con tramo de capital propio tributario negativo informado.',
             'Revisar persistencia interanual; no inferir insolvencia ni ilicitud sin contexto financiero.', record_id
      FROM cy WHERE sales_band_rank >= 9 AND trim(coalesce(negative_equity_band,'')) NOT IN ('','0','Sin Información','SIN INFORMACION')
      UNION ALL
      SELECT entity_id, 'REGION_CHANGE', cast(commercial_year AS VARCHAR),
             'LOW', 25, 'HIGH',
             'La región informada cambió respecto del año comercial anterior.',
             'Contrastar con historial de direcciones y cambios de actividad.', record_id
      FROM cy WHERE region_changed
    ),
    act_signals AS (
      SELECT entity_id, 'ACTIVITY_BREADTH' signal_type, 'CURRENT' period,
             'LOW' severity, 25 severity_score, 'HIGH' confidence,
             'Registra 6 o más actividades económicas vigentes/publicadas.' why_flagged,
             'Revisar coherencia entre giros; diversidad no constituye irregularidad por sí sola.' recommended_checks,
             '' source_record_id
      FROM read_parquet('{_q(acts_src)}')
      WHERE entity_id IS NOT NULL
      GROUP BY entity_id HAVING count(DISTINCT activity_record_id) >= 6
    ),
    addr_signals AS (
      SELECT entity_id, 'ADDRESS_HISTORY_BREADTH' signal_type, 'CURRENT' period,
             'LOW' severity, 25 severity_score, 'HIGH' confidence,
             'Historial amplio de direcciones o regiones publicadas.' why_flagged,
             'Revisar secuencia/vigencia y distinguir casa matriz de sucursales.' recommended_checks,
             '' source_record_id
      FROM read_parquet('{_q(addr_src)}')
      WHERE entity_id IS NOT NULL
      GROUP BY entity_id
      HAVING count(DISTINCT address_record_id) >= 5 OR count(DISTINCT nullif(region,'')) >= 3
    ),
    reactivation AS (
      SELECT n.entity_id, 'REACTIVATION_PATTERN' signal_type, 'CURRENT' period,
             'LOW' severity, 25 severity_score, 'HIGH' confidence,
             'Existe término de giro en el histórico y la nómina actual aparece activa según publicación.' why_flagged,
             'Reconstruir cronología de término/reinicio; tratar como evento de ciclo de vida, no ilicitud.' recommended_checks,
             '' source_record_id
      FROM (
        SELECT * EXCLUDE(rn) FROM (
          SELECT *, row_number() OVER (PARTITION BY entity_id ORDER BY legal_name_norm DESC) rn
          FROM read_parquet('{_q(names_src)}') WHERE entity_id IS NOT NULL
        ) WHERE rn=1
      ) n
      JOIN (
        SELECT entity_id, max(CASE WHEN trim(coalesce(termination_date,''))<>'' THEN 1 ELSE 0 END) has_term
        FROM cy GROUP BY entity_id
      ) h USING(entity_id)
      WHERE n.current_status='ACTIVE_AS_PUBLISHED' AND h.has_term=1
    ),
    all_signals AS (
      SELECT * FROM cy_signals UNION ALL SELECT * FROM act_signals UNION ALL SELECT * FROM addr_signals UNION ALL SELECT * FROM reactivation
    )
    SELECT concat('SII-SIG-', upper(substr(sha256(concat_ws('|',entity_id,signal_type,period,source_record_id)),1,24))) signal_id,
           *, current_timestamp generated_at
    FROM all_signals
    """
    _copy(con, sig_sql, signals_path)

    entity_search = silver_dir / "entity_search.parquet"
    entity_sql = f"""
    WITH names AS (
      SELECT * EXCLUDE(rn) FROM (
        SELECT *, row_number() OVER (PARTITION BY entity_id ORDER BY legal_name_norm DESC) rn
        FROM read_parquet('{_q(names_src)}') WHERE entity_id IS NOT NULL
      ) WHERE rn=1
    ),
    latest AS (
      SELECT * EXCLUDE(rn) FROM (
        SELECT *, row_number() OVER (PARTITION BY entity_id ORDER BY commercial_year DESC, record_id DESC) rn
        FROM read_parquet('{_q(cy_enriched)}') WHERE entity_id IS NOT NULL
      ) WHERE rn=1
    ),
    acts AS (
      SELECT entity_id, count(DISTINCT activity_record_id) activity_count,
             string_agg(DISTINCT nullif(activity_code,''), ' | ') activity_codes,
             string_agg(DISTINCT nullif(activity_name,''), ' | ') activity_names
      FROM read_parquet('{_q(acts_src)}') WHERE entity_id IS NOT NULL GROUP BY entity_id
    ),
    addr AS (
      SELECT entity_id, count(DISTINCT address_record_id) address_count,
             string_agg(DISTINCT nullif(commune,''), ' | ') communes,
             string_agg(DISTINCT nullif(region,''), ' | ') address_regions
      FROM read_parquet('{_q(addr_src)}') WHERE entity_id IS NOT NULL GROUP BY entity_id
    ),
    sig AS (
      SELECT entity_id, count(DISTINCT signal_id) signal_count, max(severity_score) max_severity_score,
             string_agg(DISTINCT signal_type, ' | ') signal_types
      FROM read_parquet('{_q(signals_path)}') GROUP BY entity_id
    )
    SELECT n.entity_id, n.rut, n.legal_name, n.legal_name_norm, n.activity_start_date, n.termination_date, n.current_status,
           l.commercial_year, l.sales_band, l.sales_band_rank, l.workers_numeric, l.region, l.economic_sector,
           l.economic_subsector, l.main_activity, l.taxpayer_type, l.taxpayer_subtype,
           l.positive_equity_band, l.negative_equity_band,
           coalesce(a.activity_count,0) activity_count, a.activity_codes, a.activity_names,
           coalesce(d.address_count,0) address_count, d.communes, d.address_regions,
           coalesce(s.signal_count,0) signal_count, coalesce(s.max_severity_score,0) max_severity_score, s.signal_types
    FROM names n
    LEFT JOIN latest l USING(entity_id)
    LEFT JOIN acts a USING(entity_id)
    LEFT JOIN addr d USING(entity_id)
    LEFT JOIN sig s USING(entity_id)
    """
    _copy(con, entity_sql, entity_search)
    return {"company_year_enriched": cy_enriched, "risk_signals": signals_path, "entity_search": entity_search}


def quality_and_dashboard(silver_dir: Path, output_dir: Path) -> tuple[dict, dict]:
    con = duckdb.connect()
    paths = {
        "company_year": silver_dir / "company_year_enriched.parquet",
        "names_current": silver_dir / "sii_names_current.parquet",
        "activities_current": silver_dir / "sii_activities_current.parquet",
        "addresses_history": silver_dir / "sii_addresses_history.parquet",
        "risk_signals": silver_dir / "risk_signals.parquet",
        "entity_search": silver_dir / "entity_search.parquet",
    }
    quality: dict[str, dict] = {}
    for name, p in paths.items():
        q = _q(p)
        row = con.execute(
            f"SELECT count(*) AS row_count, count(entity_id) AS keyed_rows, "
            f"count(DISTINCT entity_id) AS distinct_entities FROM read_parquet('{q}')"
        ).fetchone()
        quality[name] = {"rows": int(row[0]), "keyed_rows": int(row[1]), "distinct_entities": int(row[2]), "key_coverage": round(row[1] / row[0], 6) if row[0] else 0}
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "quality.json").write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")

    cy = _q(paths["company_year"])
    ent = _q(paths["entity_search"])
    sig = _q(paths["risk_signals"])
    latest_year = con.execute(f"SELECT max(commercial_year) FROM read_parquet('{cy}')").fetchone()[0]
    kpi = con.execute(f"SELECT count(DISTINCT entity_id), sum(CASE WHEN current_status='ACTIVE_AS_PUBLISHED' THEN 1 ELSE 0 END) FROM read_parquet('{ent}')").fetchone()
    signal_count = con.execute(f"SELECT count(*) FROM read_parquet('{sig}')").fetchone()[0]
    sales = dict(con.execute(f"SELECT coalesce(sales_band,'Sin información'), count(*) FROM read_parquet('{cy}') WHERE commercial_year=? GROUP BY 1 ORDER BY 2 DESC", [latest_year]).fetchall())
    regions = dict(con.execute(f"SELECT coalesce(region,'Sin información'), count(*) FROM read_parquet('{cy}') WHERE commercial_year=? GROUP BY 1 ORDER BY 2 DESC LIMIT 30", [latest_year]).fetchall())
    sigtypes = dict(con.execute(f"SELECT signal_type, count(*) FROM read_parquet('{sig}') GROUP BY 1 ORDER BY 2 DESC").fetchall())
    startyears = dict(con.execute(f"SELECT y, count(*) FROM (SELECT year(try_cast(nullif(activity_start_date,'') AS DATE)) AS y FROM read_parquet('{ent}')) t WHERE y IS NOT NULL GROUP BY y ORDER BY y DESC LIMIT 15").fetchall())
    dashboard = {
        "kpis": {"entities": int(kpi[0]), "active_as_published": int(kpi[1] or 0), "latest_company_year": int(latest_year) if latest_year is not None else None, "signals": int(signal_count)},
        "sales_bands": sales,
        "regions": regions,
        "start_years": startyears,
        "signal_types": sigtypes,
    }
    (output_dir / "dashboard.json").write_text(json.dumps(dashboard, ensure_ascii=False, indent=2), encoding="utf-8")
    return quality, dashboard
