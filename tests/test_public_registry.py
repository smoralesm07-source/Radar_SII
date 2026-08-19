from pathlib import Path

import pandas as pd

from radar_sii.public_registry import apply_public_filters, enrich_public_entities, load_public_master, load_public_registry


def _registry(path: Path) -> Path:
    df = pd.DataFrame([
        {
            "public_entity_id": "PUB-CL-1",
            "official_name": "SERVICIO PUBLICO A",
            "is_public_entity": "true",
            "is_public_service_strict": "true",
            "public_entity_type": "PUBLIC_SERVICE_OR_AGENCY",
            "source_system": "CHILECOMPRA_MERCADO_PUBLICO",
            "source_code": "1",
            "dipres_reference_match": "true",
            "entity_id": "ENT-RUT-11111111-1",
            "sii_match_method": "EXACT_NORMALIZED_NAME_UNIQUE",
            "sii_match_confidence": "HIGH",
        },
        {
            "public_entity_id": "PUB-CL-2",
            "official_name": "UNIDAD ADMINISTRATIVA A",
            "is_public_entity": "true",
            "is_public_service_strict": "false",
            "public_entity_type": "OTHER_PUBLIC_BUYER",
            "source_system": "CHILECOMPRA_MERCADO_PUBLICO",
            "source_code": "2",
            "dipres_reference_match": "false",
            "entity_id": "ENT-RUT-11111111-1",
            "sii_match_method": "EXACT_NORMALIZED_NAME_UNIQUE",
            "sii_match_confidence": "HIGH",
        },
        {
            "public_entity_id": "PUB-CL-3",
            "official_name": "SERVICIO SIN RUT RESUELTO",
            "is_public_entity": "true",
            "is_public_service_strict": "true",
            "public_entity_type": "PUBLIC_SERVICE_OR_AGENCY",
            "source_system": "CHILECOMPRA_MERCADO_PUBLICO",
            "source_code": "3",
            "dipres_reference_match": "true",
            "entity_id": "",
            "sii_match_method": "NO_RUT_MATCH",
            "sii_match_confidence": "UNMATCHED",
        },
    ])
    df.to_csv(path, sep=";", index=False, encoding="utf-8-sig")
    return path


def test_master_preserves_unmatched_public_entities(tmp_path: Path):
    p = _registry(tmp_path / "public.csv")
    master = load_public_master(p)
    matched = load_public_registry(p)
    assert len(master) == 3
    assert len(matched) == 1
    assert matched.iloc[0]["entity_id"] == "ENT-RUT-11111111-1"
    assert matched.iloc[0]["is_public_service_strict"] == "true"


def test_enrichment_does_not_multiply_sii_facts(tmp_path: Path):
    p = _registry(tmp_path / "public.csv")
    facts = pd.DataFrame([
        {"entity_id": "ENT-RUT-11111111-1", "value": 10},
        {"entity_id": "ENT-RUT-22222222-2", "value": 20},
    ])
    out = enrich_public_entities(facts, p)
    assert len(out) == 2
    first = out[out["entity_id"] == "ENT-RUT-11111111-1"].iloc[0]
    second = out[out["entity_id"] == "ENT-RUT-22222222-2"].iloc[0]
    assert bool(first["is_public_entity"]) is True
    assert bool(first["is_public_service_strict"]) is True
    assert "SERVICIO PUBLICO A" in first["public_entity_name"]
    assert bool(second["is_public_entity"]) is False


def test_public_filters_are_contextual(tmp_path: Path):
    p = _registry(tmp_path / "public.csv")
    facts = pd.DataFrame([
        {"entity_id": "ENT-RUT-11111111-1"},
        {"entity_id": "ENT-RUT-22222222-2"},
    ])
    enriched = enrich_public_entities(facts, p)
    public_only = apply_public_filters(enriched, {"is_public_entity": True})
    private_only = apply_public_filters(enriched, {"is_public_entity": False})
    assert public_only["entity_id"].tolist() == ["ENT-RUT-11111111-1"]
    assert private_only["entity_id"].tolist() == ["ENT-RUT-22222222-2"]
