from radar_sii.document_authorizations import build_observation, parse_sii_authorization_response


def test_authorized_response_extracts_date():
    status, auth_date = parse_sii_authorization_response("AUTORIZADO EL 30-12-2002.")
    assert status == "AUTHORIZED"
    assert auth_date == "2002-12-30"


def test_not_authorized_response():
    status, auth_date = parse_sii_authorization_response("DOCUMENTO NO AUTORIZADO")
    assert status == "NOT_AUTHORIZED"
    assert auth_date is None


def test_observation_uses_canonical_rut_and_entity_id():
    row = build_observation(
        rut="76.123.456-7",
        document_type_code="33",
        document_number="1001",
        document_date="2026-08-01",
        source_response="AUTORIZADO EL 02-08-2026.",
        observed_at="2026-08-19T20:00:00+00:00",
    )
    assert row.rut == "76123456-7"
    assert row.entity_id == "ENT-RUT-76123456-7"
    assert row.document_type_name == "FACTURA ELECTRONICA"
    assert row.authorization_date == "2026-08-02"
    assert row.authorization_status == "AUTHORIZED"
