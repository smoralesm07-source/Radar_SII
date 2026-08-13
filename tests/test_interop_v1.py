from radar_sii.interop import adapt_entity_record, interop_catalog


def test_entity_hub_uses_valid_rut():
    row = adapt_entity_record({"rut": "96.921.130-0", "entity_id": "ENT-RUT-96921130-0", "nombre": "Ejemplo S.A."})
    assert row["entity_id"] == "ENT-RUT-96921130-0"
    assert row["rut"] == "96921130-0"
    assert row["rut_valid"] is True
    assert row["identity_method"] == "RUT_EXACT"


def test_invalid_rut_never_creates_global_identity():
    row = adapt_entity_record({"rut": "96.921.130-1", "entity_id": "LOCAL-123", "nombre": "Ejemplo"})
    assert row["entity_id"] is None
    assert row["source_entity_id"] == "LOCAL-123"
    assert row["identity_status"] == "UNRESOLVED"


def test_role_does_not_change_identity():
    a = adapt_entity_record({"rut": "96.921.130-0"}, role="TAXPAYER")
    b = adapt_entity_record({"rut": "96.921.130-0"}, role="SUPPLIER")
    assert a["entity_id"] == b["entity_id"]
    assert a["entity_role"] != b["entity_role"]


def test_catalog_declares_native_materialization():
    catalog = interop_catalog()
    assert catalog["entity_hub_materialization"] == "NATIVE_COLUMNS_NO_DUPLICATION"
    assert any(x["grain"] == "ENTITY_X_YEAR" for x in catalog["exports"])
