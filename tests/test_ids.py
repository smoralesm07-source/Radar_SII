from radar_sii.ids import entity_id, normalize_rut, rut_is_valid


def test_rut_validation():
    assert rut_is_valid("76086428-5")
    assert normalize_rut("76.086.428-5") == "76086428-5"
    assert entity_id("76086428-5") == "ENT-RUT-76086428-5"


def test_invalid_rut_rejected():
    assert normalize_rut("76086428-0") is None
