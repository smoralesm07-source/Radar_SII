from pathlib import Path

import pandas as pd

from radar_sii.public_analysis import enrich_analytical_outputs, inject_public_metrics


def test_public_context_is_persisted_without_dropping_signals(tmp_path: Path):
    silver = tmp_path / "silver"
    silver.mkdir()
    pd.DataFrame([
        {"entity_id": "ENT-RUT-1-9", "rut": "1-9", "legal_name": "SERVICIO PUBLICO"},
        {"entity_id": "ENT-RUT-2-7", "rut": "2-7", "legal_name": "EMPRESA PRIVADA"},
    ]).to_parquet(silver / "entity_search.parquet", index=False)
    pd.DataFrame([
        {"signal_id": "S1", "entity_id": "ENT-RUT-1-9", "signal_type": "TEST", "severity_score": 50},
        {"signal_id": "S2", "entity_id": "ENT-RUT-2-7", "signal_type": "TEST", "severity_score": 50},
    ]).to_parquet(silver / "risk_signals.parquet", index=False)
    registry = tmp_path / "public.csv"
    pd.DataFrame([
        {
            "public_entity_id": "PUB-CL-A",
            "official_name": "SERVICIO PUBLICO",
            "entity_id": "ENT-RUT-1-9",
            "is_public_entity": "true",
            "is_public_service_strict": "true",
            "public_entity_type": "PUBLIC_SERVICE_OR_AGENCY",
            "source_system": "TEST",
            "source_code": "A",
        }
    ]).to_csv(registry, sep=";", index=False)

    metrics = enrich_analytical_outputs(silver, registry)
    entities = pd.read_parquet(silver / "entity_search.parquet")
    signals = pd.read_parquet(silver / "risk_signals.parquet")

    assert metrics["public_entities_matched_in_entity_search"] == 1
    assert len(signals) == 2
    public_entity = entities.loc[entities["entity_id"] == "ENT-RUT-1-9"].iloc[0]
    private_entity = entities.loc[entities["entity_id"] == "ENT-RUT-2-7"].iloc[0]
    assert bool(public_entity["is_public_entity"]) is True
    assert public_entity["analysis_population"] == "PUBLIC_ENTITY_CONTEXT"
    assert bool(public_entity["business_ranking_eligible"]) is False
    assert bool(private_entity["business_ranking_eligible"]) is True
    public_signal = signals.loc[signals["entity_id"] == "ENT-RUT-1-9"].iloc[0]
    assert public_signal["signal_applicability"] == "CONTEXT_ONLY_PUBLIC_ENTITY"
    assert bool(public_signal["business_ranking_eligible"]) is False


def test_public_metrics_are_added_to_outputs(tmp_path: Path):
    out = tmp_path / "docs"
    out.mkdir()
    (out / "quality.json").write_text('{"company_year": {}}', encoding="utf-8")
    (out / "dashboard.json").write_text('{"kpis": {"entities": 2}}', encoding="utf-8")
    metrics = {
        "enabled": True,
        "public_entities_matched_in_entity_search": 1,
        "strict_public_services_matched_in_entity_search": 1,
        "signals_public_entity_context": 3,
        "signals_total": 10,
        "registry_exists": True,
    }
    inject_public_metrics(out, metrics)
    quality = (out / "quality.json").read_text(encoding="utf-8")
    dashboard = (out / "dashboard.json").read_text(encoding="utf-8")
    assert "PUBLIC_STATUS_IS_CONTEXT_NOT_ADVERSE_SIGNAL" in quality
    assert '"public_entities_matched": 1' in dashboard
    assert '"signals_public_entity_context": 3' in dashboard
