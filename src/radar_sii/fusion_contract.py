from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

RADAR_ID = "RADAR_SII"
VERSION = "1.1"


def _evidence_id(source_id: str, sha256: str) -> str:
    seed = f"{source_id}|{sha256}".encode("utf-8")
    return "EVD-SII-" + hashlib.sha256(seed).hexdigest()[:24]


def build_fusion_contract(silver_dir: Path, output_dir: Path) -> dict[str, Any]:
    manifest_path = output_dir / "snapshot_manifest.json"
    snapshots = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else []
    if not snapshots:
        raise RuntimeError("SII snapshot manifest missing/empty; refusing lineage-free Fusion contract")

    evidence_rows: list[dict[str, Any]] = []
    evidence_by_source: dict[str, str] = {}
    for snap in snapshots:
        source_id = str(snap.get("source_id") or "").strip()
        sha = str(snap.get("sha256") or "").strip()
        retrieved = str(snap.get("downloaded_at") or "").strip()
        if not source_id or len(sha) != 64 or not retrieved:
            continue
        eid = _evidence_id(source_id, sha)
        evidence_by_source[source_id] = eid
        evidence_rows.append({
            "evidence_id": eid,
            "producer_id": RADAR_ID,
            "source_id": source_id,
            "ultimate_source_id": "SII",
            "source_url": snap.get("url") or snap.get("official_page") or None,
            "source_tier": "OFFICIAL",
            "capture_method": "RADAR_SII_OFFICIAL_BULK_SNAPSHOT",
            "source_run_id": sha[:16],
            "content_sha256": sha,
            "quality_status": "VALID",
            "source_published_at": None,
            "retrieved_at": retrieved,
            "ingested_at": retrieved,
            "schema_version": VERSION,
            "attributes": {
                "official_page": snap.get("official_page"),
                "published_update": snap.get("published_update"),
                "coverage": snap.get("coverage"),
                "normalization_version": snap.get("normalization_version"),
                "normalized_rows": snap.get("normalized_rows"),
            },
        })

    if not evidence_rows:
        raise RuntimeError("SII snapshots lack valid hash/timestamp lineage")

    evidence_path = output_dir / "evidence_fusion_v1.jsonl"
    with evidence_path.open("w", encoding="utf-8") as handle:
        for row in evidence_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    public_registry_path = Path("config/public_entities_registry.csv")
    datasets = {
        "entities": {
            "canonical_kind": "Entity",
            "path": str(silver_dir / "entity_search.parquet"),
            "format": "PARQUET_NATIVE_PROJECTION",
            "grain": "ENTITY",
            "filter": "entity_id IS NOT NULL",
            "mapping": {
                "entity_id": "entity_id",
                "entity_type": {"constant": "LEGAL_ENTITY"},
                "canonical_name": "legal_name",
                "rut_normalized": "rut",
                "roles": {"constant": ["ECONOMIC_ENTITY"]},
                "producer_ids": {"constant": [RADAR_ID]},
                "identity_method": {"constant": "RUT_EXACT"},
                "identity_confidence": {"constant": 1.0},
            },
            "context_enrichment": {
                "public_entity_registry_dataset": "public_entities_registry",
                "join_key": "entity_id",
                "fields": [
                    "is_public_entity",
                    "is_public_service_strict",
                    "public_entity_type",
                    "official_name",
                    "gob_cl_reference_match",
                    "chilecompra_reference_match",
                    "datos_gob_reference_match",
                    "dipres_reference_match",
                    "source_system",
                    "source_code",
                    "sii_match_method",
                    "sii_match_confidence",
                ],
                "semantics": "PUBLIC_STATUS_IS_CONTEXT_NOT_ADVERSE_SIGNAL",
            },
            "evidence_ids": [evidence_by_source.get("sii_names_current"), evidence_by_source.get("sii_company_year")],
        },
        "public_entities_registry": {
            "canonical_kind": "EntityContext",
            "path": str(public_registry_path),
            "format": "CSV_SEMICOLON_UTF8",
            "grain": "PUBLIC_ADMINISTRATIVE_ENTITY",
            "optional": True,
            "entity_key": "entity_id",
            "public_key": "public_entity_id",
            "attributes": [
                "official_name",
                "is_public_entity",
                "is_public_service_strict",
                "public_entity_type",
                "source_system",
                "source_code",
                "gob_cl_reference_match",
                "chilecompra_reference_match",
                "datos_gob_reference_match",
                "dipres_reference_match",
                "rut",
                "sii_match_method",
                "sii_match_confidence",
            ],
            "identity_policy": "RUT_ENTITY_ID_ONLY_ON_EXACT_NORMALIZED_UNIQUE_SII_NAME_MATCH",
            "unmatched_policy": "PRESERVE_PUBLIC_ENTITY_WITHOUT_FORCED_RUT_LINK",
            "source_semantics": {
                "strict_public_service_reference": "GOB_CL_EXPLICIT_PUBLIC_SERVICES_LIST",
                "broad_procurement_universe": "CHILECOMPRA_MERCADO_PUBLICO_BUYER_REGISTRY",
                "complementary_institution_directory": "DATOS_GOB_INSTITUTIONS",
                "budget_corroboration": "DIPRES_INSTITUTIONAL_BUDGET_REFERENCE",
            },
            "adverse_signal": False,
        },
        "company_year": {
            "canonical_kind": "Event",
            "event_type": "ECONOMIC_SNAPSHOT",
            "path": str(silver_dir / "company_year_enriched.parquet"),
            "format": "PARQUET_NATIVE_PROJECTION",
            "grain": "ENTITY_X_COMMERCIAL_YEAR",
            "entity_key": "entity_id",
            "event_key": "record_id",
            "valid_time_field": "commercial_year",
            "attributes": ["sales_band", "sales_band_code", "workers_numeric", "region", "province", "commune", "economic_sector", "economic_subsector", "main_activity", "taxpayer_type", "taxpayer_subtype", "positive_equity_band", "negative_equity_band"],
            "evidence_ids": [evidence_by_source.get("sii_company_year")],
        },
        "activities": {
            "canonical_kind": "Event",
            "event_type": "ECONOMIC_ACTIVITY_REGISTRATION",
            "path": str(silver_dir / "sii_activities_current.parquet"),
            "format": "PARQUET_NATIVE_PROJECTION",
            "grain": "ENTITY_X_ACTIVITY",
            "entity_key": "entity_id",
            "event_key": "activity_record_id",
            "valid_time_field": "activity_registration_date",
            "attributes": ["activity_code", "activity_name", "vat_affected", "activity_category", "activity_status"],
            "evidence_ids": [evidence_by_source.get("sii_activities_current")],
        },
        "addresses": {
            "canonical_kind": "Event",
            "event_type": "ADDRESS_OBSERVATION",
            "path": str(silver_dir / "sii_addresses_history.parquet"),
            "format": "PARQUET_NATIVE_PROJECTION",
            "grain": "ENTITY_X_ADDRESS_PERIOD",
            "entity_key": "entity_id",
            "event_key": "address_record_id",
            "valid_time_field": "address_date",
            "attributes": ["address_status", "address_type", "street", "street_number", "city", "locality", "commune", "region"],
            "territory_policy": "FREE_TEXT_CONTEXT_ONLY_UNTIL_CANONICAL_CODE_AVAILABLE",
            "evidence_ids": [evidence_by_source.get("sii_addresses_history")],
        },
        "ownership": {
            "canonical_kind": "Relationship",
            "path": str(silver_dir / "sii_ownership_current.parquet"),
            "format": "PARQUET_NATIVE_PROJECTION",
            "grain": "OWNERSHIP_EDGE",
            "filter": "entity_id IS NOT NULL AND partner_entity_id IS NOT NULL",
            "relationship_id": "ownership_record_id",
            "source_entity_id": "entity_id",
            "target_entity_id": "partner_entity_id",
            "relationship_type": {"constant": "OWNERSHIP_AS_PUBLISHED"},
            "assertion_type": {"constant": "OBSERVED"},
            "confidence": {"constant": 1.0},
            "attributes": ["ownership_percent", "society_type", "society_subtype", "partner_id_type"],
            "unresolved_policy": "NATURAL_PERSONS_AGGREGATE_OR_MISSING_PARTNER_NOT_PROMOTED_AS_ENTITY_RELATIONSHIP",
            "evidence_ids": [evidence_by_source.get("sii_ownership_current")],
        },
        "radar_signals": {
            "canonical_kind": "RADAR_SIGNAL_CANDIDATE",
            "path": str(silver_dir / "risk_signals.parquet"),
            "format": "PARQUET_NATIVE",
            "policy": "DO_NOT_AUTO_PROMOTE_TO_SIG_AML_REGISTRY",
            "reason": "SII local analytical flags require cross-radar context before becoming AML signals",
            "public_entity_policy": {
                "analysis_population": "PUBLIC_ENTITY_CONTEXT",
                "business_ranking_eligible": False,
                "signal_applicability": "CONTEXT_ONLY_PUBLIC_ENTITY",
                "preserve_original_signal": True,
            },
        },
    }
    for dataset in datasets.values():
        if isinstance(dataset.get("evidence_ids"), list):
            dataset["evidence_ids"] = [x for x in dataset["evidence_ids"] if x]

    contract = {
        "interop_version": VERSION,
        "radar_id": RADAR_ID,
        "status": "FUSION_CONTRACT_READY_NATIVE_PARQUET",
        "canonical_consumer": "smoralesm07-source/Intelligence_Fusion_Layer",
        "materialization_policy": "NO_DUPLICATION_FOR_MULTI_MILLION_ROW_SII_FACTS",
        "global_entity_key": "ENT-RUT-{RUT_NORMALIZADO}",
        "source_failure_is_zero": False,
        "guardrails": [
            "SII_ACTIVITY_DOES_NOT_PROVE_UAF_OBLIGED_STATUS",
            "SII_ACTIVITY_OR_OSFL_MEMBERSHIP_IS_NOT_ADVERSE_BY_ITSELF",
            "PUBLIC_ENTITY_STATUS_IS_CONTEXT_NOT_ADVERSE_SIGNAL",
            "PUBLIC_ENTITY_RUT_IS_NOT_INFERRED_BY_FUZZY_NAME_MATCH",
            "GOB_CL_PUBLIC_SERVICE_MEMBERSHIP_IS_INSTITUTIONAL_CONTEXT_NOT_RISK",
            "MISSING_SOURCE_IS_NOT_ZERO",
            "PRESERVE_SOURCE_SNAPSHOT_HASH_AND_RETRIEVAL_TIME",
        ],
        "datasets": datasets,
        "evidence_path": str(evidence_path),
    }
    (output_dir / "fusion_contract_v1.json").write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
    status = {
        "interop_version": VERSION,
        "radar_id": RADAR_ID,
        "status": contract["status"],
        "source_evidence_records": len(evidence_rows),
        "datasets": {
            name: (Path(spec["path"]).exists() if spec.get("path") else None)
            for name, spec in datasets.items()
        },
        "source_failure_is_zero": False,
    }
    (output_dir / "fusion_interop_status_v1.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    return status
