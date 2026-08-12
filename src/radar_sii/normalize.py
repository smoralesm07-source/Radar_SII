from __future__ import annotations

import csv
import json
import re
import unicodedata
from pathlib import Path
from typing import Iterable

import pandas as pd

from .ids import clean_text, deterministic_id, entity_id, normalize_name, normalize_rut


def slug(value: object) -> str:
    text = clean_text(value).upper()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^A-Z0-9]+", "_", text).strip("_").lower()
    return text or "unnamed"


def detect_encoding(path: Path) -> str:
    sample = path.read_bytes()[:200_000]
    for enc in ("utf-8-sig", "cp1252", "latin1"):
        try:
            sample.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin1"


def detect_separator(path: Path, encoding: str) -> str:
    sample = path.read_bytes()[:100_000].decode(encoding, errors="replace")
    try:
        return csv.Sniffer().sniff(sample, delimiters="\t;|,").delimiter
    except csv.Error:
        counts = {sep: sample.count(sep) for sep in ("\t", ";", "|", ",")}
        return max(counts, key=counts.get)


def read_chunks(path: Path, chunksize: int = 100_000) -> Iterable[pd.DataFrame]:
    encoding = detect_encoding(path)
    sep = detect_separator(path, encoding)
    yield from pd.read_csv(
        path,
        sep=sep,
        encoding=encoding,
        dtype=str,
        chunksize=chunksize,
        low_memory=False,
        on_bad_lines="skip",
    )


def _canonicalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    seen: dict[str, int] = {}
    names: list[str] = []
    for col in result.columns:
        base = slug(col)
        n = seen.get(base, 0)
        seen[base] = n + 1
        names.append(base if n == 0 else f"{base}_{n+1}")
    result.columns = names
    return result


def _coalesce(df: pd.DataFrame, aliases: list[str], default: object = "") -> pd.Series:
    for name in aliases:
        if name in df.columns:
            return df[name].fillna("").astype(str)
    return pd.Series([default] * len(df), index=df.index, dtype="object")


def _parse_one_date(value: object) -> str:
    text = clean_text(value)
    if not text:
        return ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        parsed = pd.to_datetime(text, format="%Y-%m-%d", errors="coerce")
    elif re.fullmatch(r"\d{2}-\d{2}-\d{4}", text):
        parsed = pd.to_datetime(text, format="%d-%m-%Y", errors="coerce")
    elif re.fullmatch(r"\d{2}/\d{2}/\d{4}", text):
        parsed = pd.to_datetime(text, format="%d/%m/%Y", errors="coerce")
    else:
        parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        return ""
    return parsed.strftime("%Y-%m-%d")


def _parse_date(series: pd.Series) -> pd.Series:
    return series.map(_parse_one_date).astype("object")


def _rut_from_aliases(df: pd.DataFrame, rut_aliases: list[str], dv_aliases: list[str]) -> pd.Series:
    rut_raw = _coalesce(df, rut_aliases)
    dv_raw = _coalesce(df, dv_aliases)
    return pd.Series([normalize_rut(r, d) for r, d in zip(rut_raw, dv_raw)], index=df.index, dtype="object")


def _rut_series(df: pd.DataFrame) -> pd.Series:
    return _rut_from_aliases(
        df,
        ["rut", "rut_contribuyente", "rut_empresa", "numero_rut", "rut_numero"],
        ["dv", "digito_verificador", "dv_rut"],
    )


def normalize_company_year(df: pd.DataFrame, source_id: str = "sii_company_year") -> pd.DataFrame:
    df = _canonicalize_columns(df)
    out = df.add_prefix("src_")
    out["rut"] = _rut_series(df)
    out["entity_id"] = out["rut"].map(entity_id)
    out["commercial_year"] = pd.to_numeric(_coalesce(df, ["ano_comercial", "anio_comercial", "ano", "year"]), errors="coerce").astype("Int64")
    out["legal_name"] = _coalesce(df, ["razon_social", "nombre_razon_social", "nombre"])
    out["legal_name_norm"] = out["legal_name"].map(normalize_name)
    out["sales_band"] = _coalesce(df, ["tramo_segun_ventas", "tramo_ventas", "tramo_venta"])
    out["sales_band_code"] = pd.to_numeric(out["sales_band"], errors="coerce").astype("Int64")
    out["workers"] = pd.to_numeric(
        _coalesce(
            df,
            [
                "numero_de_trabajadores_dependie",
                "numero_trabajadores_dependientes",
                "numero_de_trabajadores_dependientes",
                "nro_trabajadores",
                "trabajadores",
            ],
        ),
        errors="coerce",
    ).astype("Int64")
    out["region"] = _coalesce(df, ["region", "region_empresa"])
    out["province"] = _coalesce(df, ["provincia"])
    out["commune"] = _coalesce(df, ["comuna"])
    out["economic_sector"] = _coalesce(df, ["rubro_economico", "rubro"])
    out["economic_subsector"] = _coalesce(df, ["subrubro_economico", "sub_rubro_economico", "subrubro"])
    out["main_activity"] = _coalesce(df, ["actividad_economica", "actividad_economica_principal", "actividad_principal"])
    out["activity_start_date"] = _parse_date(
        _coalesce(
            df,
            [
                "fecha_inicio_de_actividades_vige",
                "fecha_inicio_actividades_vigentes",
                "fecha_inicio_actividades",
                "fecha_inicio_actividad",
            ],
        )
    )
    out["first_activity_registration_date"] = _parse_date(
        _coalesce(df, ["fecha_primera_inscripcion_de_ac", "fecha_primera_inscripcion_actividad"])
    )
    out["termination_date"] = _parse_date(
        _coalesce(df, ["fecha_termino_de_giro", "fecha_termino_giro", "fecha_de_termino_de_giro"])
    )
    out["termination_type"] = _coalesce(df, ["tipo_termino_de_giro", "tipo_termino_giro", "tipo_de_termino_de_giro"])
    out["taxpayer_type"] = _coalesce(df, ["tipo_de_contribuyente", "tipo_contribuyente"])
    out["taxpayer_subtype"] = _coalesce(df, ["subtipo_de_contribuyente", "subtipo_contribuyente", "sub_tipo_contribuyente"])
    out["positive_equity_band"] = _coalesce(df, ["tramo_capital_propio_positivo", "tramo_cpt_positivo", "capital_propio_positivo"])
    out["negative_equity_band"] = _coalesce(df, ["tramo_capital_propio_negativo", "tramo_cpt_negativo", "capital_propio_negativo"])
    out["presumptive_income_regime"] = _coalesce(df, ["r_presunta"])
    out["other_tax_regimes"] = _coalesce(df, ["otros_regimenes"])
    out["source_id"] = source_id
    out["record_id"] = [deterministic_id("SII-CY", r, y) for r, y in zip(out["rut"], out["commercial_year"])]
    return out


def normalize_names(df: pd.DataFrame, source_id: str = "sii_names_current") -> pd.DataFrame:
    df = _canonicalize_columns(df)
    out = df.add_prefix("src_")
    out["rut"] = _rut_series(df)
    out["entity_id"] = out["rut"].map(entity_id)
    out["taxpayer_subtype_code"] = _coalesce(df, ["cod_subtipo", "codigo_subtipo"])
    out["legal_name"] = _coalesce(df, ["razon_social", "nombre_razon_social", "nombre"])
    out["legal_name_norm"] = out["legal_name"].map(normalize_name)
    out["activity_start_date"] = _parse_date(
        _coalesce(df, ["fecha_inicio_vig", "fecha_inicio_de_actividades_vige", "fecha_inicio_actividades_vigentes", "fecha_inicio_actividades"])
    )
    out["termination_date"] = _parse_date(
        _coalesce(df, ["fecha_tg_vig", "fecha_termino_de_giro", "fecha_termino_giro", "fecha_de_termino_de_giro"])
    )
    out["current_status"] = out["termination_date"].map(lambda x: "ACTIVE_AS_PUBLISHED" if not x else "TERMINATED_AS_PUBLISHED")
    out["source_id"] = source_id
    out["record_id"] = [deterministic_id("SII-NAME", r, n) for r, n in zip(out["rut"], out["legal_name_norm"])]
    return out


def normalize_activities(df: pd.DataFrame, source_id: str = "sii_activities_current") -> pd.DataFrame:
    df = _canonicalize_columns(df)
    out = df.add_prefix("src_")
    out["rut"] = _rut_series(df)
    out["entity_id"] = out["rut"].map(entity_id)
    out["activity_code"] = _coalesce(df, ["codigo_actividad", "codigo_actividad_economica", "actividad_codigo", "codigo"])
    out["activity_name"] = _coalesce(df, ["desc_actividad_economica", "actividad_economica", "glosa_actividad", "descripcion_actividad", "actividad"])
    out["activity_registration_date"] = _parse_date(_coalesce(df, ["fecha", "fecha_actividad", "fecha_inscripcion"]))
    out["vat_affected"] = _coalesce(df, ["afecta_a_iva", "afecta_iva"])
    out["activity_category"] = _coalesce(df, ["categoria_tributaria", "categoria"])
    status = _coalesce(df, ["vigencia", "estado", "estado_actividad"], default="VIGENTE_AS_PUBLISHED")
    out["activity_status"] = status.replace("", "VIGENTE_AS_PUBLISHED")
    out["source_id"] = source_id
    out["activity_record_id"] = [deterministic_id("SII-ACT", r, c, n, d) for r, c, n, d in zip(out["rut"], out["activity_code"], out["activity_name"], out["activity_registration_date"])]
    return out


def normalize_addresses(df: pd.DataFrame, source_id: str = "sii_addresses_history") -> pd.DataFrame:
    df = _canonicalize_columns(df)
    out = df.add_prefix("src_")
    out["rut"] = _rut_series(df)
    out["entity_id"] = out["rut"].map(entity_id)
    out["address_status"] = _coalesce(df, ["vigencia", "estado", "estado_direccion"])
    out["address_date"] = _parse_date(_coalesce(df, ["fecha", "fecha_direccion"]))
    out["address_type"] = _coalesce(df, ["tipo_direccion", "tipo_de_direccion", "tipo"])
    out["street"] = _coalesce(df, ["calle", "direccion", "nombre_calle"])
    out["street_number"] = _coalesce(df, ["numero", "numero_direccion", "nro"])
    out["block"] = _coalesce(df, ["bloque"])
    out["apartment"] = _coalesce(df, ["departamento", "depto"])
    out["village"] = _coalesce(df, ["villa_poblacion"])
    out["city"] = _coalesce(df, ["ciudad"])
    out["locality"] = _coalesce(df, ["villa_poblacion", "ciudad", "localidad"])
    out["commune"] = _coalesce(df, ["comuna"])
    out["region"] = _coalesce(df, ["region"])
    out["source_id"] = source_id
    out["address_record_id"] = [
        deterministic_id("SII-ADR", r, t, d, s, n, c, reg)
        for r, t, d, s, n, c, reg in zip(
            out["rut"], out["address_type"], out["address_date"], out["street"], out["street_number"], out["commune"], out["region"]
        )
    ]
    return out


def normalize_ownership(df: pd.DataFrame, source_id: str = "sii_ownership_current") -> pd.DataFrame:
    df = _canonicalize_columns(df)
    out = df.add_prefix("src_")
    out["rut"] = _rut_from_aliases(df, ["rut_sociedad"], ["dv_sociedad"])
    out["entity_id"] = out["rut"].map(entity_id)
    out["society_type"] = _coalesce(df, ["tipo_sociedad"])
    out["society_subtype"] = _coalesce(df, ["subtipo_sociedad"])
    out["partner_rut"] = _rut_from_aliases(df, ["rut_socio"], ["dv_socio"])
    out["partner_entity_id"] = out["partner_rut"].map(entity_id)
    out["natural_person_group_source"] = _coalesce(df, ["id_personas_naturales"])
    out["partner_id_type"] = [
        "RUT" if r else ("NATURAL_PERSONS_AGGREGATE" if clean_text(g) else "MISSING")
        for r, g in zip(out["partner_rut"], out["natural_person_group_source"])
    ]
    out["partner_group_id"] = out["natural_person_group_source"].map(lambda x: "PERSONAS_NATURALES" if clean_text(x) else "")
    pct = _coalesce(df, ["participacion"]).str.replace("%", "", regex=False).str.replace(",", ".", regex=False)
    out["ownership_percent"] = pd.to_numeric(pct, errors="coerce")
    out["relationship_type"] = "OWNERSHIP_AS_PUBLISHED"
    out["source_id"] = source_id
    out["ownership_record_id"] = [
        deterministic_id("SII-OWN", r, pr, pg, p)
        for r, pr, pg, p in zip(out["rut"], out["partner_rut"], out["partner_group_id"], out["ownership_percent"])
    ]
    return out


def normalize_chunk(df: pd.DataFrame, kind: str, source_id: str) -> pd.DataFrame:
    funcs = {
        "company_year": normalize_company_year,
        "names": normalize_names,
        "activities": normalize_activities,
        "addresses": normalize_addresses,
        "ownership": normalize_ownership,
    }
    if kind not in funcs:
        raise ValueError(f"Tipo de fuente no soportado: {kind}")
    result = funcs[kind](df, source_id=source_id)
    result["source_payload_schema"] = json.dumps(sorted(df.columns.tolist()), ensure_ascii=False)
    return result
