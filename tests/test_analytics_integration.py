from pathlib import Path

import pandas as pd

from radar_sii.analytics import build_analytics, quality_and_dashboard


def _write(df: pd.DataFrame, path: Path) -> None:
    df.to_parquet(path, index=False)


def test_build_analytics_end_to_end(tmp_path: Path):
    silver = tmp_path / "silver"
    out = tmp_path / "out"
    silver.mkdir()
    eid = "ENT-RUT-76086428-5"

    _write(pd.DataFrame([
        {
            "entity_id": eid, "rut": "76086428-5", "commercial_year": 2023, "record_id": "cy23",
            "sales_band": "6", "sales_band_code": 6, "workers": 20, "activity_start_date": "2021-01-01",
            "region": "METROPOLITANA", "province": "SANTIAGO", "commune": "SANTIAGO",
            "economic_sector": "SERVICIOS", "economic_subsector": "OTROS", "main_activity": "SERVICIOS",
            "taxpayer_type": "PJ", "taxpayer_subtype": "SPA", "positive_equity_band": "3",
            "negative_equity_band": "", "first_activity_registration_date": "2021-01-01",
            "termination_date": "", "presumptive_income_regime": "N", "other_tax_regimes": "",
        },
        {
            "entity_id": eid, "rut": "76086428-5", "commercial_year": 2024, "record_id": "cy24",
            "sales_band": "10", "sales_band_code": 10, "workers": 2, "activity_start_date": "2021-01-01",
            "region": "METROPOLITANA", "province": "SANTIAGO", "commune": "SANTIAGO",
            "economic_sector": "COMERCIO", "economic_subsector": "OTROS", "main_activity": "COMERCIO",
            "taxpayer_type": "PJ", "taxpayer_subtype": "SPA", "positive_equity_band": "4",
            "negative_equity_band": "", "first_activity_registration_date": "2021-01-01",
            "termination_date": "", "presumptive_income_regime": "N", "other_tax_regimes": "",
        },
    ]), silver / "sii_company_year.parquet")

    _write(pd.DataFrame([{
        "entity_id": eid, "rut": "76086428-5", "record_id": "n1", "legal_name": "Empresa Demo SpA",
        "legal_name_norm": "EMPRESA DEMO SPA", "taxpayer_subtype_code": "101", "activity_start_date": "2021-01-01",
        "termination_date": "", "current_status": "ACTIVE_AS_PUBLISHED",
    }]), silver / "sii_names_current.parquet")

    _write(pd.DataFrame([{
        "entity_id": eid, "activity_record_id": "a1", "activity_code": "620200", "activity_name": "SERVICIOS TI",
        "activity_registration_date": "2021-01-01", "vat_affected": "S", "activity_category": "1",
    }]), silver / "sii_activities_current.parquet")

    _write(pd.DataFrame([{
        "entity_id": eid, "address_record_id": "d1", "commune": "SANTIAGO", "region": "METROPOLITANA",
        "address_status": "S", "address_date": "2021-01-01",
    }]), silver / "sii_addresses_history.parquet")

    _write(pd.DataFrame([{
        "entity_id": eid, "ownership_record_id": "o1", "partner_entity_id": "ENT-RUT-11111111-1",
        "partner_id_type": "RUT", "society_type": "SOCIEDAD", "society_subtype": "SPA", "ownership_percent": 60.0,
    }]), silver / "sii_ownership_current.parquet")

    paths = build_analytics(silver)
    quality, dashboard = quality_and_dashboard(silver, out)

    assert paths["entity_search"].exists()
    assert paths["risk_signals"].exists()
    assert quality["company_year"]["years"] == [2023, 2024]
    assert quality["ownership_current"]["rows"] == 1
    assert dashboard["kpis"]["entities"] == 1
    assert dashboard["kpis"]["ownership_edges"] == 1
