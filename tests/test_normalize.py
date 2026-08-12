import pandas as pd

from radar_sii.normalize import normalize_company_year, normalize_names


def test_company_year_aliases():
    df = pd.DataFrame([{ "RUT": "76086428", "DV": "5", "AÑO COMERCIAL": "2024", "RAZON SOCIAL": "Empresa Demo SpA", "TRAMO SEGUN VENTAS": "100.000,01 a 200.000 UF", "NUMERO TRABAJADORES DEPENDIENTES": "2", "FECHA INICIO ACTIVIDADES VIGENTES": "01-03-2023" }])
    out = normalize_company_year(df)
    assert out.loc[0, "rut"] == "76086428-5"
    assert int(out.loc[0, "commercial_year"]) == 2024
    assert int(out.loc[0, "workers"]) == 2


def test_current_status():
    df = pd.DataFrame([{ "RUT": "76086428-5", "RAZON SOCIAL": "Empresa Demo SpA", "FECHA TERMINO GIRO": "" }])
    out = normalize_names(df)
    assert out.loc[0, "current_status"] == "ACTIVE_AS_PUBLISHED"
