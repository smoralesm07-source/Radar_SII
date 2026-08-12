from __future__ import annotations

import json
from pathlib import Path

import duckdb


def _q(path: Path) -> str:
    return str(path).replace("'", "''")


def _ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def canonicalize_company_year(silver_dir: Path) -> dict:
    """Preserva el hecho fuente y genera una vista canónica entity_id+commercial_year.

    SII contiene un número muy pequeño de duplicados entity-year que, en el perfil 2020-2024,
    difieren sólo en fecha de término de giro. La vista canónica nunca elige silenciosamente
    entre fechas incompatibles: conserva todas las variantes en columnas de auditoría y deja
    la fecha canónica vacía cuando existe conflicto.

    Si dos filas del mismo entity-year difieren en cualquier otro campo fuente/canónico,
    el pipeline falla para evitar seleccionar arbitrariamente un hecho empresarial.
    """
    canonical_path = silver_dir / "sii_company_year.parquet"
    source_path = silver_dir / "sii_company_year_source.parquet"
    conflict_path = silver_dir / "company_year_stable_conflicts.parquet"
    if not canonical_path.exists():
        raise FileNotFoundError(canonical_path)
    source_path.unlink(missing_ok=True)
    canonical_path.replace(source_path)

    con = duckdb.connect()
    qsrc = _q(source_path)
    cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{qsrc}')").fetchall()]
    required = {"entity_id", "commercial_year", "termination_date"}
    missing = required - set(cols)
    if missing:
        raise RuntimeError(f"Faltan columnas company_year para canonicalización: {sorted(missing)}")

    # Cualquier diferencia distinta de la fecha de término de giro se considera conflicto estable.
    ignored = {"termination_date", "src_fecha_termino_de_giro", "record_id", "source_payload_schema"}
    stable_cols = [c for c in cols if c not in ignored]
    payload_parts = ", ".join(
        f"coalesce(cast({_ident(c)} AS VARCHAR), '<NULL>')" for c in stable_cols
    )
    payload_hash = f"sha256(concat_ws(chr(31), {payload_parts}))"
    conflict_sql = f"""
      WITH source AS (
        SELECT *, {payload_hash} AS stable_payload_hash
        FROM read_parquet('{qsrc}')
        WHERE entity_id IS NOT NULL AND commercial_year IS NOT NULL
      )
      SELECT entity_id, commercial_year, count(*) AS source_rows,
             count(DISTINCT stable_payload_hash) AS stable_payload_variants
      FROM source
      GROUP BY entity_id, commercial_year
      HAVING count(DISTINCT stable_payload_hash) > 1
    """
    conflict_path.unlink(missing_ok=True)
    con.execute(f"COPY ({conflict_sql}) TO '{_q(conflict_path)}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    stable_conflicts = int(con.execute(f"SELECT count(*) FROM ({conflict_sql})").fetchone()[0])

    source_stats = con.execute(f"""
      WITH d AS (
        SELECT entity_id, commercial_year, count(*) AS c,
               count(DISTINCT coalesce(nullif(trim(termination_date),''), '<EMPTY>')) AS term_variants
        FROM read_parquet('{qsrc}')
        WHERE entity_id IS NOT NULL AND commercial_year IS NOT NULL
        GROUP BY entity_id, commercial_year
      )
      SELECT count(*) FILTER (WHERE c>1) AS duplicate_groups,
             coalesce(sum(c-1) FILTER (WHERE c>1),0) AS duplicate_extra_rows,
             count(*) FILTER (WHERE term_variants>1) AS termination_conflict_groups
      FROM d
    """).fetchone()

    if stable_conflicts:
        quality = {
            "source_rows": int(con.execute(f"SELECT count(*) FROM read_parquet('{qsrc}')").fetchone()[0]),
            "stable_payload_conflict_groups": stable_conflicts,
            "source_duplicate_entity_year_groups": int(source_stats[0] or 0),
            "source_duplicate_entity_year_rows": int(source_stats[1] or 0),
            "termination_date_conflict_groups": int(source_stats[2] or 0),
        }
        (silver_dir / "company_year_source_quality.json").write_text(
            json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        raise RuntimeError(
            f"SII company_year contiene {stable_conflicts} grupos entity-year con conflictos fuera de fecha término; "
            f"revise {conflict_path}"
        )

    # Estadísticas por llave y una sola fila de fuente representativa. Como ya comprobamos
    # que el payload estable es idéntico dentro del grupo, la fila base no introduce arbitrariedad.
    stats_sql = f"""
      SELECT entity_id, commercial_year,
             count(*) AS source_row_count,
             count(DISTINCT coalesce(nullif(trim(termination_date),''), '<EMPTY>')) AS termination_date_variant_count,
             string_agg(DISTINCT coalesce(nullif(trim(termination_date),''), '<EMPTY>'), ' | ' ORDER BY coalesce(nullif(trim(termination_date),''), '<EMPTY>')) AS termination_date_values,
             max(CASE WHEN trim(coalesce(termination_date,''))<>'' THEN 1 ELSE 0 END) AS has_termination_source
      FROM read_parquet('{qsrc}')
      WHERE entity_id IS NOT NULL AND commercial_year IS NOT NULL
      GROUP BY entity_id, commercial_year
    """
    select_parts: list[str] = []
    for c in cols:
        if c == "termination_date":
            select_parts.append(
                "CASE WHEN s.termination_date_variant_count=1 THEN r.termination_date ELSE '' END AS termination_date"
            )
        elif c == "src_fecha_termino_de_giro":
            select_parts.append(
                "CASE WHEN s.termination_date_variant_count=1 THEN r.src_fecha_termino_de_giro ELSE '' END AS src_fecha_termino_de_giro"
            )
        else:
            select_parts.append(f"r.{_ident(c)}")
    select_parts.extend([
        "s.source_row_count",
        "s.termination_date_variant_count",
        "s.termination_date_values",
        "s.termination_date_variant_count > 1 AS termination_date_conflict",
        "s.has_termination_source > 0 AS has_termination_source",
    ])
    select_sql = ",\n             ".join(select_parts)
    canonical_sql = f"""
      WITH ranked AS (
        SELECT *, row_number() OVER (
          PARTITION BY entity_id, commercial_year
          ORDER BY coalesce(termination_date,''), record_id
        ) AS rn
        FROM read_parquet('{qsrc}')
      ), stats AS ({stats_sql})
      SELECT {select_sql}
      FROM ranked r
      JOIN stats s USING(entity_id, commercial_year)
      WHERE r.rn=1
    """
    con.execute(f"COPY ({canonical_sql}) TO '{_q(canonical_path)}' (FORMAT PARQUET, COMPRESSION ZSTD)")

    source_rows = int(con.execute(f"SELECT count(*) FROM read_parquet('{qsrc}')").fetchone()[0])
    canonical_rows = int(con.execute(f"SELECT count(*) FROM read_parquet('{_q(canonical_path)}')").fetchone()[0])
    canonical_dups = int(con.execute(f"""
      SELECT coalesce(sum(c-1),0) FROM (
        SELECT entity_id, commercial_year, count(*) c
        FROM read_parquet('{_q(canonical_path)}')
        GROUP BY 1,2 HAVING count(*)>1
      )
    """).fetchone()[0])
    quality = {
        "source_rows": source_rows,
        "canonical_rows": canonical_rows,
        "source_duplicate_entity_year_groups": int(source_stats[0] or 0),
        "source_duplicate_entity_year_rows": int(source_stats[1] or 0),
        "termination_date_conflict_groups": int(source_stats[2] or 0),
        "stable_payload_conflict_groups": stable_conflicts,
        "canonical_duplicate_entity_year_rows": canonical_dups,
    }
    (silver_dir / "company_year_source_quality.json").write_text(
        json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return quality
