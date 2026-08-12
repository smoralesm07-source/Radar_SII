import pandas as pd

from radar_sii.features import enrich_company_year
from radar_sii.signals import signals_from_company_year


def test_sales_jump_and_workforce_signal():
    df = pd.DataFrame([
        {"record_id":"a", "entity_id":"ENT-RUT-76086428-5", "commercial_year":2023, "sales_band":"600,01 a 2.400 UF", "workers":2, "activity_start_date":"2023-01-01", "region":"RM", "negative_equity_band":""},
        {"record_id":"b", "entity_id":"ENT-RUT-76086428-5", "commercial_year":2024, "sales_band":"100.000,01 a 200.000 UF", "workers":2, "activity_start_date":"2023-01-01", "region":"RM", "negative_equity_band":""},
    ])
    enriched = enrich_company_year(df)
    sig = signals_from_company_year(enriched)
    assert "SALES_BAND_JUMP" in set(sig["signal_type"])
    assert "HIGH_SALES_LOW_WORKFORCE" in set(sig["signal_type"])
