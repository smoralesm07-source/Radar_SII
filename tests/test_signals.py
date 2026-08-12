import pandas as pd

from radar_sii.features import enrich_company_year, sales_band_rank
from radar_sii.signals import signals_from_company_year


def test_sii_sales_code_semantics():
    assert sales_band_rank("1") == 1
    assert sales_band_rank("10") == 10
    assert sales_band_rank("13") == 13
    assert sales_band_rank("Sin Información") == 1


def test_sales_jump_workforce_and_activity_signals():
    df = pd.DataFrame([
        {
            "record_id": "a", "entity_id": "ENT-RUT-76086428-5", "commercial_year": 2023,
            "sales_band": "6", "sales_band_code": 6, "workers": 20, "activity_start_date": "2021-01-01",
            "region": "RM", "main_activity": "SERVICIOS", "negative_equity_band": "",
        },
        {
            "record_id": "b", "entity_id": "ENT-RUT-76086428-5", "commercial_year": 2024,
            "sales_band": "10", "sales_band_code": 10, "workers": 2, "activity_start_date": "2021-01-01",
            "region": "RM", "main_activity": "COMERCIO", "negative_equity_band": "",
        },
    ])
    enriched = enrich_company_year(df)
    sig = signals_from_company_year(enriched)
    types = set(sig["signal_type"])
    assert "SALES_BAND_JUMP" in types
    assert "HIGH_SALES_LOW_WORKFORCE" in types
    assert "WORKFORCE_DROP_STABLE_SALES" in types
    assert "MAIN_ACTIVITY_CHANGE" in types


def test_unknown_sales_band_is_not_a_jump_baseline():
    df = pd.DataFrame([
        {"record_id":"a", "entity_id":"ENT-RUT-76086428-5", "commercial_year":2023, "sales_band":"1", "sales_band_code":1, "workers":2, "activity_start_date":"2020-01-01", "region":"RM", "main_activity":"SERVICIOS", "negative_equity_band":""},
        {"record_id":"b", "entity_id":"ENT-RUT-76086428-5", "commercial_year":2024, "sales_band":"10", "sales_band_code":10, "workers":2, "activity_start_date":"2020-01-01", "region":"RM", "main_activity":"SERVICIOS", "negative_equity_band":""},
    ])
    sig = signals_from_company_year(enrich_company_year(df))
    assert "SALES_BAND_JUMP" not in set(sig["signal_type"])
