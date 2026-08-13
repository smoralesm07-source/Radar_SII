from __future__ import annotations

from typing import Any

from .ids import entity_id as canonical_entity_id
from .ids import normalize_rut

INTEROP_VERSION = "1.0"
RADAR_ID = "RADAR_SII"


def adapt_entity_record(record: dict[str, Any], role: str = "ECONOMIC_ENTITY") -> dict[str, Any]:
    """Project an SII record onto the cross-radar Entity Hub contract.

    SII already stores the canonical RUT/entity_id in its native facts. The adapter
    deliberately does not invent an identity when the RUT is missing or invalid.
    """
    rut = normalize_rut(record.get("rut") or record.get("RUT"))
    eid = canonical_entity_id(rut)
    source_id = record.get("entity_id") or record.get("source_entity_id") or ""
    name = (
        record.get("canonical_name")
        or record.get("razon_social")
        or record.get("nombre")
        or record.get("name")
        or ""
    )
    normalized_name = record.get("normalized_name") or str(name).strip().upper()
    resolved = bool(eid)
    return {
        "interop_version": INTEROP_VERSION,
        "radar_id": RADAR_ID,
        "entity_id": eid,
        "source_entity_id": source_id or eid or None,
        "entity_type": record.get("entity_type") or "LEGAL_ENTITY",
        "entity_role": role,
        "rut": rut,
        "rut_valid": resolved,
        "canonical_name": name,
        "normalized_name": normalized_name,
        "identity_status": "RESOLVED" if resolved else "UNRESOLVED",
        "identity_method": "RUT_EXACT" if resolved else "SOURCE_LOCAL_ONLY",
        "identity_confidence": 1.0 if resolved else 0.0,
    }


def interop_catalog() -> dict[str, Any]:
    """Small machine-readable catalog; heavy SII facts remain in Actions artifacts."""
    return {
        "interop_version": INTEROP_VERSION,
        "radar_id": RADAR_ID,
        "entity_hub_materialization": "NATIVE_COLUMNS_NO_DUPLICATION",
        "global_entity_key": "ENT-RUT-{RUT_NORMALIZADO}",
        "unresolved_policy": "ENTITY_ID_NULL_CANDIDATE_ONLY",
        "exports": [
            {"dataset": "company_year", "grain": "ENTITY_X_YEAR", "entity_key": "entity_id"},
            {"dataset": "legal_entities/names", "grain": "ENTITY", "entity_key": "entity_id"},
            {"dataset": "entity_activities", "grain": "ENTITY_X_ACTIVITY", "entity_key": "entity_id"},
            {"dataset": "entity_addresses", "grain": "ENTITY_X_ADDRESS_PERIOD", "entity_key": "entity_id"},
            {"dataset": "ownership_edges", "grain": "OWNERSHIP_EDGE", "entity_key": "entity_id"},
        ],
        "consumer_note": "Use native Parquet outputs from GitHub Actions artifacts; entity_id is already canonical when RUT is valid.",
    }
