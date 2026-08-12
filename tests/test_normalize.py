import pandas as pd

from radar_sii.normalize import normalize_company_year, normalize_names, normalize_ownership


def test_company_year_real_sii_headers():
    df = pd.DataFrame([{
        "Año comercial": "2024",
        "RUT": "76086428",
        "DV": "5",
        "Razón social": "Empresa Demo SpA",
        "Tramo según ventas": "10",
        "Número de trabajadores dependie": "2",
        "Fecha inicio de actividades vige": "2023-03-01",
        "Fecha primera inscripción de ac": "2023-03-01",
        "Región": "METROPOLITANA",
        "Provincia": "SANTIAGO",
        "Comuna": "SANTIAGO",
    }])
    out = normalize_company_year(df)
    assert out.loc[0, "rut"] == "76086428-5"
    assert int(out.loc[0, "commercial_year"]) == 2024
    assert int(out.loc[0, "sales_band_code"]) == 10
    assert int(out.loc[0, "workers"]) == 2
    assert out.loc[0, "activity_start_date"] == "2023-03-01"
    assert out.loc[0, "province"] == "SANTIAGO"


def test_invalid_rut_dv_is_not_promoted_to_entity():
    df = pd.DataFrame([{
        "Año comercial": "2024",
        "RUT": "76086428",
        "DV": "9",
        "Razón social": "Empresa con DV inválido",
        "Tramo según ventas": "4",
    }])
    out = normalize_company_year(df)
    assert out.loc[0, "rut"] is None
    assert out.loc[0, "entity_id"] is None


def test_names_real_sii_dates_and_status():
    df = pd.DataFrame([{
        "RUT": "76086428",
        "DV": "5",
        "COD_SUBTIPO": "101",
        "RAZON_SOCIAL": "Empresa Demo SpA",
        "FECHA_INICIO_VIG": "01-03-2023",
        "FECHA_TG_VIG": "",
    }])
    out = normalize_names(df)
    assert out.loc[0, "current_status"] == "ACTIVE_AS_PUBLISHED"
    assert out.loc[0, "activity_start_date"] == "2023-03-01"
    assert out.loc[0, "taxpayer_subtype_code"] == "101"


def test_ownership_does_not_invent_natural_person_identity():
    df = pd.DataFrame([{
        "Rut Sociedad": "76086428",
        "DV Sociedad": "5",
        "Tipo Sociedad": "SOCIEDAD",
        "Subtipo Sociedad": "SPA",
        "RUT Socio": "",
        "DV Socio": "",
        "ID Personas Naturales": "Personas Naturales",
        "Participación": "100",
    }])
    out = normalize_ownership(df)
    assert out.loc[0, "entity_id"] == "ENT-RUT-76086428-5"
    assert out.loc[0, "partner_entity_id"] is None
    assert out.loc[0, "partner_id_type"] == "NATURAL_PERSONS_AGGREGATE"
    assert out.loc[0, "partner_group_id"] == "PERSONAS_NATURALES"
    assert float(out.loc[0, "ownership_percent"]) == 100.0
