from pathlib import Path

import pandas as pd
import pytest

from radar_sii.company_year import canonicalize_company_year


def _base(term: str, workers: int = 10) -> dict:
    return {
        "entity_id": "ENT-RUT-76086428-5",
        "rut": "76086428-5",
        "commercial_year": 2024,
        "record_id": "SII-CY-76086428-5-2024",
        "legal_name": "EMPRESA DEMO SPA",
        "sales_band": "8",
        "sales_band_code": 8,
        "workers": workers,
        "region": "METROPOLITANA",
        "province": "SANTIAGO",
        "commune": "SANTIAGO",
        "economic_sector": "SERVICIOS",
        "economic_subsector": "OTROS",
        "main_activity": "SERVICIOS",
        "activity_start_date": "2020-01-01",
        "first_activity_registration_date": "2020-01-01",
        "termination_date": term,
        "src_fecha_termino_de_giro": term,
        "source_payload_schema": "[]",
        "source_id": "sii_company_year",
    }


def test_termination_date_variants_collapse_only_in_canonical_view(tmp_path: Path):
    silver = tmp_path / "silver"
    silver.mkdir()
    raw = pd.DataFrame([_base("2024-01-10"), _base("2024-02-20")])
    raw.to_parquet(silver / "sii_company_year.parquet", index=False)

    q = canonicalize_company_year(silver)

    source = pd.read_parquet(silver / "sii_company_year_source.parquet")
    canonical = pd.read_parquet(silver / "sii_company_year.parquet")
    assert len(source) == 2
    assert len(canonical) == 1
    assert canonical.loc[0, "termination_date"] == ""
    assert bool(canonical.loc[0, "termination_date_conflict"]) is True
    assert bool(canonical.loc[0, "has_termination_source"]) is True
    assert "2024-01-10" in canonical.loc[0, "termination_date_values"]
    assert "2024-02-20" in canonical.loc[0, "termination_date_values"]
    assert q["source_duplicate_entity_year_rows"] == 1
    assert q["termination_date_conflict_groups"] == 1
    assert q["stable_payload_conflict_groups"] == 0
    assert q["canonical_duplicate_entity_year_rows"] == 0


def test_business_field_conflict_stops_pipeline(tmp_path: Path):
    silver = tmp_path / "silver"
    silver.mkdir()
    raw = pd.DataFrame([_base("2024-01-10", workers=10), _base("2024-01-10", workers=20)])
    raw.to_parquet(silver / "sii_company_year.parquet", index=False)

    with pytest.raises(RuntimeError, match="conflictos fuera de fecha término"):
        canonicalize_company_year(silver)
