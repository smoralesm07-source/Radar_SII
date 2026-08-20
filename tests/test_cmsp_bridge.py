import pandas as pd

from radar_sii.cmsp_bridge import document_code, prepare_cmsp_records


def test_document_code_conservative_mapping():
    assert document_code("FACTURA ELECTRONICA") == "33"
    assert document_code("Nota de crédito electrónica") == "61"
    assert document_code("documento desconocido") is None


def test_prepare_cmsp_records_from_public_spend_shape():
    df = pd.DataFrame([
        {
            "rut_beneficiario": "76.123.456-0",
            "tipo_documento": "FACTURA ELECTRONICA",
            "numero_documento": "1001",
            "fecha_documento": "19-08-2026",
        },
        {
            "rut_beneficiario": "76.123.456-0",
            "tipo_documento": "FACTURA ELECTRONICA",
            "numero_documento": "1001",
            "fecha_documento": "19-08-2026",
        },
    ])
    rows, meta = prepare_cmsp_records(df)
    assert rows == [["76123456", "0", "33", "1001", "20260819"]]
    assert meta["prepared_records"] == 1
    assert meta["skipped"]["duplicate"] == 1
