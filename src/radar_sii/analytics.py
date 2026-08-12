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


def _sales_rank_sql(col: str = "sales_band", code_col: str = "sales_band_code") -> str:
    """Return SII's published ordinal 1..13; 1 means Sin información."""
    u = f"upper(coalesce(cast({col} as varchar),''))"
    return f"""
    COALESCE(
      try_cast({code_col} AS INTEGER),
      try_cast({col} AS INTEGER),
      CASE
        WHEN {u} LIKE '%MAS DE 1.000.000%' OR {u} LIKE '%MÁS DE 1.000.000%' OR {u} LIKE '%1.000.000,01%' THEN 13
        WHEN {u} LIKE '%600.000,01%' THEN 12
        WHEN {u} LIKE '%200.000,01%' THEN 11
        WHEN {u} LIKE '%100.000,01%' THEN 10
        WHEN {u} LIKE '%50.000,01%' THEN 9
        WHEN {u} LIKE '%25.000,01%' THEN 8
        WHEN {u} LIKE '%10.000,01%' THEN 7
        WHEN {u} LIKE '%5.000,01%' THEN 6
        WHEN {u} LIKE '%2.400,01%' THEN 5
        WHEN {u} LIKE '%600,01%' THEN 4
        WHEN {u} LIKE '%200,01%' THEN 3
        WHEN {u} LIKE '%0,01%' THEN 2
        WHEN {u} LIKE '%SIN INFORMACION%' OR {u} LIKE '%SIN INFORMACIÓN%' OR {u} LIKE '%SIN VENTAS%' THEN 1
        ELSE NULL
      END
    )
    """


def build_analytics(silver_dir: Path) -> dict:
    con = duckdb.connect()
    cy_src = silver_dir / "sii_company_year.parquet"
    names_src = silver_dir / "sii_names_current.parquet"
    acts_src = silver_dir / "sii_activities_current.parquet"
    addr_src = silver_dir / "sii_addresses_history.parquet"
    own_src = silver_dir / "sii_ownership_current.parquet"
    required = [cy_src, names_src, acts_src, addr_src, own_src]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Faltan fuentes normalizadas: {missing}")

    cy_enriched = silver_dir / "company_year_enriched.parquet"
    sales_rank = _sales_rank_sql("sales_band", "sales_band_code")
    cy_sql = f"""
    WITH base AS (
      SELECT *,
             {sales_rank} AS sales_band_rank,
             try_cast(workers AS BIGINT) AS workers_numeric,
             commercial_year - year(try_cast(nullif(activity_start_date,'') AS DATE)) AS entity_age_years
      FROM read_parquet('{_q(cy_src)}')
    ), lagged AS (
      SELECT *,
             lag(sales_band_rank) OVER (PARTITION BY entity_id ORDER BY commercial_year, record_id) AS prior_sales_band_rank,
             lag(workers_numeric) OVER (PARTITION BY entity_id ORDER BY commercial_year, record_id) AS prior_workers_numeric,
             lag(region) OVER (PARTITION BY entity_id ORDER BY commercial_year, record_id) AS prior_region,
             lag(main_activity) OVER (PARTITION BY entity_id ORDER BY commercial_year, record_id) AS prior_main_activity
      FROM base
    )
    SELECT *,
           CASE WHEN sales_band_rank > 1 AND prior_sales_band_rank > 1 THEN sales_band_rank - prior_sales_band_rank END AS sales_band_delta,
           CASE WHEN prior_region IS NOT NULL AND coalesce(region,'') <> coalesce(prior_region,'') THEN TRUE ELSE FALSE END AS region_changed,
           CASE WHEN nullif(trim(prior_main_activity),'') IS NOT NULL
                     AND nullif(trim(main_activity),'') IS NOT NULL
                     AND trim(main_activity) <> trim(prior_main_activity)
                THEN TRUE ELSE FALSE END AS main_activity_changed,
           CASE WHEN prior_workers_numeric > 0 THEN workers_numeric::DOUBLE / prior_workers_numeric END AS workforce_ratio
    FROM lagged
    """
    _copy(con, cy_sql, cy_enriched)

    signals_path = silver_dir / "risk_signals.parquet"
    sig_sql = f"""
    WITH cy AS (
      SELECT * FROM read_parquet('{_q(cy_enriched)}')
    ),
    current_names AS (
      SELECT * EXCLUDE(rn) FROM (
        SELECT *, row_number() OVER (PARTITION BY entity_id ORDER BY record_id DESC) rn
        FROM read_parquet('{_q(names_src)}')
        WHERE entity_id IS NOT NULL
      ) t
      WHERE rn=1
    ),
    hist_term AS (
      SELECT cy.entity_id AS entity_id,
             max(CASE WHEN trim(coalesce(cy.termination_date,''))<>'' THEN 1 ELSE 0 END) AS has_term
      FROM cy
      WHERE cy.entity_id IS NOT NULL
      GROUP BY cy.entity_id
    ),
    cy_signals AS (
      SELECT entity_id, 'SALES_BAND_JUMP' signal_type, cast(commercial_year AS VARCHAR) period,
             'MEDIUM' severity, 50 severity_score, 'HIGH' confidence,
             'El tramo de ventas SII aumentó al menos 3 niveles respecto del año anterior con información.' why_flagged,
             'Comparar con pares del mismo rubro y revisar continuidad de actividad, dotación y contrapartes en otros radares.' recommended_checks,
             record_id source_record_id
      FROM cy WHERE sales_band_delta >= 3
      UNION ALL
      SELECT entity_id, 'HIGH_SALES_LOW_WORKFORCE', cast(commercial_year AS VARCHAR),
             'MEDIUM', 50, 'MEDIUM',
             'Tramo SII de gran empresa con 2 o menos trabajadores dependientes informados.',
             'Contextualizar por industria y modelo operativo; revisar evolución de trabajadores, actividades y domicilios.', record_id
      FROM cy WHERE sales_band_rank >= 10 AND workers_numeric <= 2
      UNION ALL
      SELECT entity_id, 'RECENT_START_HIGH_SALES', cast(commercial_year AS VARCHAR),
             'MEDIUM', 50, 'MEDIUM',
             'Empresa con hasta 2 años desde el inicio publicado y tramo SII de gran empresa.',
             'Validar historia societaria y cruzar con contratación pública/CGR cuando corresponda.', record_id
      FROM cy WHERE sales_band_rank >= 10 AND entity_age_years BETWEEN 0 AND 2
      UNION ALL
      SELECT entity_id, 'HIGH_SALES_NEGATIVE_EQUITY', cast(commercial_year AS VARCHAR),
             'MEDIUM', 50, 'MEDIUM',
             'Tramo SII de gran empresa coexistiendo con tramo de capital propio tributario negativo informado.',
             'Revisar persistencia interanual; no inferir insolvencia ni ilicitud sin contexto financiero.', record_id
      FROM cy WHERE sales_band_rank >= 10 AND trim(coalesce(negative_equity_band,'')) NOT IN ('','0','Sin Información','SIN INFORMACION')
      UNION ALL
      SELECT entity_id, 'WORKFORCE_DROP_STABLE_SALES', cast(commercial_year AS VARCHAR),
             'MEDIUM', 50, 'MEDIUM',
             'La dotación informada cayó al 20% o menos del año anterior mientras el tramo de ventas no disminuyó.',
             'Revisar externalización, estacionalidad, reorganizaciones y continuidad operacional antes de interpretar el patrón.', record_id
      FROM cy
      WHERE prior_workers_numeric >= 10 AND workers_numeric >= 0
        AND workforce_ratio <= 0.20
        AND sales_band_rank > 1 AND prior_sales_band_rank > 1
        AND sales_band_rank >= prior_sales_band_rank
      UNION ALL
      SELECT entity_id, 'MAIN_ACTIVITY_CHANGE', cast(commercial_year AS VARCHAR),
             'LOW', 25, 'HIGH',
             'La actividad económica principal informada cambió respecto del año comercial anterior.',
             'Contrastar con actividades vigentes, fecha de inscripción y evolución de ventas/dotación.', record_id
      FROM cy WHERE main_activity_changed
      UNION ALL
      SELECT entity_id, 'REGION_CHANGE', cast(commercial_year AS VARCHAR),
             'LOW', 25, 'HIGH',
             'La región informada cambió respecto del año comercial anterior.',
             'Contrastar con historial de direcciones; la localización SII puede corresponder a casa matriz.', record_id
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
      FROM current_names n
      INNER JOIN hist_term h ON h.entity_id = n.entity_id
      WHERE n.current_status='ACTIVE_AS_PUBLISHED' AND h.has_term=1
    ),
    all_signals AS (
      SELECT * FROM cy_signals
      UNION ALL SELECT * FROM act_signals
      UNION ALL SELECT * FROM addr_signals
      UNION ALL SELECT * FROM reactivation
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
        SELECT *, row_number() OVER (PARTITION BY entity_id ORDER BY record_id DESC) rn
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
             string_agg(DISTINCT nullif(activity_name,''), ' | ') activity_names,
             max(try_cast(nullif(activity_registration_date,'') AS DATE)) latest_activity_registration_date
      FROM read_parquet('{_q(acts_src)}') WHERE entity_id IS NOT NULL GROUP BY entity_id
    ),
    addr AS (
      SELECT entity_id, count(DISTINCT address_record_id) address_count,
             count(DISTINCT address_record_id) FILTER (WHERE upper(trim(address_status))='S') current_address_count,
             string_agg(DISTINCT nullif(commune,''), ' | ') communes,
             string_agg(DISTINCT nullif(region,''), ' | ') address_regions,
             max(try_cast(nullif(address_date,'') AS DATE)) latest_address_date
      FROM read_parquet('{_q(addr_src)}') WHERE entity_id IS NOT NULL GROUP BY entity_id
    ),
    own_out AS (
      SELECT entity_id, count(DISTINCT ownership_record_id) ownership_edge_count,
             count(DISTINCT partner_entity_id) FILTER (WHERE partner_entity_id IS NOT NULL) legal_entity_partner_count,
             max(CASE WHEN partner_id_type='NATURAL_PERSONS_AGGREGATE' THEN 1 ELSE 0 END) has_natural_person_aggregate,
             any_value(society_type) society_type,
             any_value(society_subtype) society_subtype
      FROM read_parquet('{_q(own_src)}') WHERE entity_id IS NOT NULL GROUP BY entity_id
    ),
    own_in AS (
      SELECT partner_entity_id entity_id, count(DISTINCT entity_id) societies_as_partner_count
      FROM read_parquet('{_q(own_src)}') WHERE partner_entity_id IS NOT NULL GROUP BY partner_entity_id
    ),
    sig AS (
      SELECT entity_id, count(DISTINCT signal_id) signal_count, max(severity_score) max_severity_score,
             string_agg(DISTINCT signal_type, ' | ') signal_types
      FROM read_parquet('{_q(signals_path)}') GROUP BY entity_id
    )
    SELECT n.entity_id, n.rut, n.legal_name, n.legal_name_norm, n.taxpayer_subtype_code,
           n.activity_start_date, n.termination_date, n.current_status,
           l.commercial_year, l.sales_band, l.sales_band_code, l.sales_band_rank, l.workers_numeric,
           l.region, l.province, l.commune, l.economic_sector, l.economic_subsector, l.main_activity,
           l.taxpayer_type, l.taxpayer_subtype, l.positive_equity_band, l.negative_equity_band,
           l.first_activity_registration_date, l.presumptive_income_regime, l.other_tax_regimes,
           coalesce(a.activity_count,0) activity_count, a.activity_codes, a.activity_names, a.latest_activity_registration_date,
           coalesce(d.address_count,0) address_count, coalesce(d.current_address_count,0) current_address_count,
           d.communes, d.address_regions, d.latest_address_date,
           coalesce(o.ownership_edge_count,0) ownership_edge_count,
           coalesce(o.legal_entity_partner_count,0) legal_entity_partner_count,
           coalesce(o.has_natural_person_aggregate,0) has_natural_person_aggregate,
           o.society_type, o.society_subtype,
           coalesce(i.societies_as_partner_count,0) societies_as_partner_count,
           coalesce(s.signal_count,0) signal_count, coalesce(s.max_severity_score,0) max_severity_score, s.signal_types
    FROM names n
    LEFT JOIN latest l USING(entity_id)
    LEFT JOIN acts a USING(entity_id)
    LEFT JOIN addr d USING(entity_id)
    LEFT JOIN own_out o USING(entity_id)
    LEFT JOIN own_in i USING(entity_id)
    LEFT JOIN sig s USING(entity_id)
    """
    _copy(con, entity_sql, entity_search)
    return {
        "company_year_enriched": cy_enriched,
        "risk_signals": signals_path,
        "entity_search": entity_search,
        "ownership_edges": own_src,
    }


def _base_quality(con: duckdb.DuckDBPyConnection, p: Path) -> dict:
    q = _q(p)
    row = con.execute(
        f"SELECT count(*) AS row_count, count(entity_id) AS keyed_rows, "
        f"count(DISTINCT entity_id) AS distinct_entities FROM read_parquet('{q}')"
    ).fetchone()
    return {
        "rows": int(row[0]),
        "keyed_rows": int(row[1]),
        "distinct_entities": int(row[2]),
        "key_coverage": round(row[1] / row[0], 6) if row[0] else 0,
    }


def quality_and_dashboard(silver_dir: Path, output_dir: Path) -> tuple[dict, dict]:
    con = duckdb.connect()
    paths = {
        "company_year": silver_dir / "company_year_enriched.parquet",
        "names_current": silver_dir / "sii_names_current.parquet",
        "activities_current": silver_dir / "sii_activities_current.parquet",
        "addresses_history": silver_dir / "sii_addresses_history.parquet",
        "ownership_current": silver_dir / "sii_ownership_current.parquet",
        "risk_signals": silver_dir / "risk_signals.parquet",
        "entity_search": silver_dir / "entity_search.parquet",
    }
    quality: dict[str, dict] = {name: _base_quality(con, p) for name, p in paths.items()}

    cy = _q(paths["company_year"])
    names = _q(paths["names_current"])
    acts = _q(paths["activities_current"])
    addr = _q(paths["addresses_history"])
    own = _q(paths["ownership_current"])
    ent = _q(paths["entity_search"])
    sig = _q(paths["risk_signals"])

    years = [int(r[0]) for r in con.execute(f"SELECT DISTINCT commercial_year FROM read_parquet('{cy}') WHERE commercial_year IS NOT NULL ORDER BY 1").fetchall()]
    dup = con.execute(f"SELECT coalesce(sum(c-1),0) FROM (SELECT entity_id, commercial_year, count(*) c FROM read_parquet('{cy}') GROUP BY 1,2 HAVING count(*)>1)").fetchone()[0]
    cy_cov = con.execute(
        f"SELECT count(sales_band_code), count(workers_numeric), count(nullif(activity_start_date,'')), count(nullif(region,'')), count(nullif(main_activity,'')) FROM read_parquet('{cy}')"
    ).fetchone()
    quality["company_year"].update({
        "years": years,
        "duplicate_entity_year_rows": int(dup or 0),
        "sales_band_coverage": round(cy_cov[0] / quality["company_year"]["rows"], 6),
        "workers_coverage": round(cy_cov[1] / quality["company_year"]["rows"], 6),
        "activity_start_date_coverage": round(cy_cov[2] / quality["company_year"]["rows"], 6),
        "region_coverage": round(cy_cov[3] / quality["company_year"]["rows"], 6),
        "main_activity_coverage": round(cy_cov[4] / quality["company_year"]["rows"], 6),
    })

    nstats = con.execute(
        f"SELECT count(nullif(activity_start_date,'')), count(nullif(termination_date,'')), count(nullif(taxpayer_subtype_code,'')) FROM read_parquet('{names}')"
    ).fetchone()
    quality["names_current"].update({
        "activity_start_date_coverage": round(nstats[0] / quality["names_current"]["rows"], 6),
        "terminated_as_published": int(nstats[1]),
        "taxpayer_subtype_code_coverage": round(nstats[2] / quality["names_current"]["rows"], 6),
    })

    astats = con.execute(
        f"SELECT count(nullif(activity_code,'')), count(nullif(activity_name,'')), count(nullif(activity_registration_date,'')), count(nullif(vat_affected,'')) FROM read_parquet('{acts}')"
    ).fetchone()
    quality["activities_current"].update({
        "activity_code_coverage": round(astats[0] / quality["activities_current"]["rows"], 6),
        "activity_name_coverage": round(astats[1] / quality["activities_current"]["rows"], 6),
        "activity_date_coverage": round(astats[2] / quality["activities_current"]["rows"], 6),
        "vat_flag_coverage": round(astats[3] / quality["activities_current"]["rows"], 6),
    })

    dstats = con.execute(
        f"SELECT count(nullif(address_date,'')), count(nullif(address_status,'')), count(nullif(commune,'')), count(nullif(region,'')), sum(CASE WHEN upper(trim(address_status))='S' THEN 1 ELSE 0 END) FROM read_parquet('{addr}')"
    ).fetchone()
    quality["addresses_history"].update({
        "address_date_coverage": round(dstats[0] / quality["addresses_history"]["rows"], 6),
        "status_coverage": round(dstats[1] / quality["addresses_history"]["rows"], 6),
        "commune_coverage": round(dstats[2] / quality["addresses_history"]["rows"], 6),
        "region_coverage": round(dstats[3] / quality["addresses_history"]["rows"], 6),
        "current_addresses": int(dstats[4] or 0),
    })

    ostats = con.execute(
        f"SELECT count(partner_entity_id), sum(CASE WHEN partner_id_type='NATURAL_PERSONS_AGGREGATE' THEN 1 ELSE 0 END), "
        f"sum(CASE WHEN partner_id_type='MISSING' THEN 1 ELSE 0 END), count(ownership_percent), "
        f"sum(CASE WHEN ownership_percent < 0 OR ownership_percent > 100 THEN 1 ELSE 0 END) FROM read_parquet('{own}')"
    ).fetchone()
    quality["ownership_current"].update({
        "legal_entity_partner_edges": int(ostats[0] or 0),
        "natural_person_aggregate_edges": int(ostats[1] or 0),
        "missing_partner_edges": int(ostats[2] or 0),
        "ownership_percent_coverage": round((ostats[3] or 0) / quality["ownership_current"]["rows"], 6),
        "ownership_percent_out_of_bounds": int(ostats[4] or 0),
    })

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "quality.json").write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")

    latest_year = con.execute(f"SELECT max(commercial_year) FROM read_parquet('{cy}')").fetchone()[0]
    earliest_year = con.execute(f"SELECT min(commercial_year) FROM read_parquet('{cy}')").fetchone()[0]
    kpi = con.execute(
        f"SELECT count(DISTINCT entity_id), sum(CASE WHEN current_status='ACTIVE_AS_PUBLISHED' THEN 1 ELSE 0 END), "
        f"sum(CASE WHEN current_status='TERMINATED_AS_PUBLISHED' THEN 1 ELSE 0 END) FROM read_parquet('{ent}')"
    ).fetchone()
    signal_count = con.execute(f"SELECT count(*) FROM read_parquet('{sig}')").fetchone()[0]
    own_kpi = con.execute(
        f"SELECT count(*), count(DISTINCT entity_id), count(partner_entity_id) FROM read_parquet('{own}')"
    ).fetchone()
    sales = dict(con.execute(
        f"SELECT coalesce(sales_band,'Sin información') AS band, count(*) AS n FROM read_parquet('{cy}') "
        f"WHERE commercial_year=? GROUP BY band ORDER BY try_cast(band AS INTEGER)",
        [latest_year],
    ).fetchall())
    regions = dict(con.execute(f"SELECT coalesce(region,'Sin información'), count(*) FROM read_parquet('{cy}') WHERE commercial_year=? GROUP BY 1 ORDER BY 2 DESC LIMIT 30", [latest_year]).fetchall())
    sigtypes = dict(con.execute(f"SELECT signal_type, count(*) FROM read_parquet('{sig}') GROUP BY 1 ORDER BY 2 DESC").fetchall())
    startyears = dict(con.execute(f"SELECT y, count(*) FROM (SELECT year(try_cast(nullif(activity_start_date,'') AS DATE)) AS y FROM read_parquet('{ent}')) t WHERE y IS NOT NULL GROUP BY y ORDER BY y DESC LIMIT 20").fetchall())
    history = dict(con.execute(f"SELECT commercial_year, count(DISTINCT entity_id) FROM read_parquet('{cy}') GROUP BY 1 ORDER BY 1").fetchall())
    dashboard = {
        "kpis": {
            "entities": int(kpi[0]),
            "active_as_published": int(kpi[1] or 0),
            "terminated_as_published": int(kpi[2] or 0),
            "earliest_company_year": int(earliest_year) if earliest_year is not None else None,
            "latest_company_year": int(latest_year) if latest_year is not None else None,
            "signals": int(signal_count),
            "ownership_edges": int(own_kpi[0]),
            "ownership_societies": int(own_kpi[1]),
            "ownership_legal_entity_links": int(own_kpi[2]),
        },
        "history_entities": history,
        "sales_bands": sales,
        "regions": regions,
        "start_years": startyears,
        "signal_types": sigtypes,
    }
    (output_dir / "dashboard.json").write_text(json.dumps(dashboard, ensure_ascii=False, indent=2), encoding="utf-8")
    return quality, dashboard
