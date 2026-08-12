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


def _parse_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series.replace("", pd.NA), dayfirst=True, errors="coerce").dt.strftime("%Y-%m-%d").fillna("")


def _rut_series(df: pd.DataFrame) -> pd.Series:
    rut_raw = _coalesce(df, ["rut", "rut_contribuyente", "rut_empresa", "numero_rut", "rut_numero"])
    dv_raw = _coalesce(df, ["dv", "digito_verificador", "dv_rut"])
    return pd.Series([normalize_rut(r, d) for r, d in zip(rut_raw, dv_raw)], index=df.index, dtype="object")


def normalize_company_year(df: pd.DataFrame, source_id: str = "sii_company_year") -> pd.DataFrame:
    df = _canonicalize_columns(df)
    out = df.add_prefix("src_")
    out["rut"] = _rut_series(df)
    out["entity_id"] = out["rut"].map(entity_id)
    out["commercial_year"] = pd.to_numeric(_coalesce(df, ["ano_comercial", "anio_comercial", "ano", "year"]), errors="coerce").astype("Int64")
    out["legal_name"] = _coalesce(df, ["razon_social", "nombre_razon_social", "nombre"])
    out["legal_name_norm"] = out["legal_name"].map(normalize_name)
    out["sales_band"] = _coalesce(df, ["tramo_segun_ventas", "tramo_ventas", "tramo_venta"])
    out["workers"] = pd.to_numeric(_coalesce(df, ["numero_trabajadores_dependientes", "numero_de_trabajadores_dependientes", "nro_trabajadores", "trabajadores"]), errors="coerce").astype("Int64")
    out["region"] = _coalesce(df, ["region", "region_empresa"])
    out["economic_sector"] = _coalesce(df, ["rubro_economico", "rubro"])
    out["economic_subsector"] = _coalesce(df, ["subrubro_economico", "sub_rubro_economico", "subrubro"])
    out["main_activity"] = _coalesce(df, ["actividad_economica", "actividad_economica_principal", "actividad_principal"])
    out["activity_start_date"] = _parse_date(_coalesce(df, ["fecha_inicio_actividades_vigentes", "fecha_inicio_actividades", "fecha_inicio_actividad"] ))
    out["termination_date"] = _parse_date(_coalesce(df, ["fecha_termino_giro", "fecha_de_termino_de_giro"] ))
    out["termination_type"] = _coalesce(df, ["tipo_termino_giro", "tipo_de_termino_de_giro"])
    out["taxpayer_type"] = _coalesce(df, ["tipo_contribuyente", "tipo_de_contribuyente"])
    out["taxpayer_subtype"] = _coalesce(df, ["subtipo_contribuyente", "sub_tipo_contribuyente", "subtipo_de_contribuyente"])
    out["positive_equity_band"] = _coalesce(df, ["tramo_capital_propio_positivo", "tramo_cpt_positivo", "capital_propio_positivo"])
    out["negative_equity_band"] = _coalesce(df, ["tramo_capital_propio_negativo", "tramo_cpt_negativo", "capital_propio_negativo"])
    out["source_id"] = source_id
    out["record_id"] = [deterministic_id("SII-CY", r, y) for r, y in zip(out["rut"], out["commercial_year"])]
    return out


def normalize_names(df: pd.DataFrame, source_id: str = "sii_names_current") -> pd.DataFrame:
    df = _canonicalize_columns(df)
    out = df.add_prefix("src_")
    out["rut"] = _rut_series(df)
    out["entity_id"] = out["rut"].map(entity_id)
    out["legal_name"] = _coalesce(df, ["razon_social", "nombre_razon_social", "nombre"])
    out["legal_name_norm"] = out["legal_name"].map(normalize_name)
    out["activity_start_date"] = _parse_date(_coalesce(df, ["fecha_inicio_actividades_vigentes", "fecha_inicio_actividades", "fecha_inicio_actividad"] ))
    out["termination_date"] = _parse_date(_coalesce(df, ["fecha_termino_giro", "fecha_de_termino_de_giro"] ))
    out["current_status"] = out["termination_date"].map(lambda x: "ACTIVE_AS_PUBLISHED" if not x else "TERMINATED_AS_PUBLISHED")
    out["source_id"] = source_id
    return out


def normalize_activities(df: pd.DataFrame, source_id: str = "sii_activities_current") -> pd.DataFrame:
    df = _canonicalize_columns(df)
    out = df.add_prefix("src_")
    out["rut"] = _rut_series(df)
    out["entity_id"] = out["rut"].map(entity_id)
    out["activity_code"] = _coalesce(df, ["codigo_actividad", "codigo_actividad_economica", "actividad_codigo", "codigo"])
    out["activity_name"] = _coalesce(df, ["actividad_economica", "glosa_actividad", "descripcion_actividad", "actividad"])
    out["activity_category"] = _coalesce(df, ["categoria_tributaria", "categoria"])
    out["activity_status"] = _coalesce(df, ["vigencia", "estado", "estado_actividad"], default="VIGENTE_AS_PUBLISHED")
    out["source_id"] = source_id
    out["activity_record_id"] = [deterministic_id("SII-ACT", r, c, n) for r, c, n in zip(out["rut"], out["activity_code"], out["activity_name"])]
    return out


def normalize_addresses(df: pd.DataFrame, source_id: str = "sii_addresses_history") -> pd.DataFrame:
    df = _canonicalize_columns(df)
    out = df.add_prefix("src_")
    out["rut"] = _rut_series(df)
    out["entity_id"] = out["rut"].map(entity_id)
    out["address_type"] = _coalesce(df, ["tipo_direccion", "tipo_de_direccion", "tipo"])
    out["street"] = _coalesce(df, ["calle", "direccion", "nombre_calle"])
    out["street_number"] = _coalesce(df, ["numero", "numero_direccion", "nro"])
    out["block"] = _coalesce(df, ["bloque"])
    out["apartment"] = _coalesce(df, ["departamento", "depto"])
    out["locality"] = _coalesce(df, ["villa_poblacion", "ciudad", "localidad"])
    out["commune"] = _coalesce(df, ["comuna"])
    out["region"] = _coalesce(df, ["region"])
    out["address_status"] = _coalesce(df, ["vigencia", "estado", "estado_direccion"])
    out["source_id"] = source_id
    out["address_record_id"] = [deterministic_id("SII-ADR", r, t, s, n, c, reg) for r, t, s, n, c, reg in zip(out["rut"], out["address_type"], out["street"], out["street_number"], out["commune"], out["region"])]
    return out


def normalize_chunk(df: pd.DataFrame, kind: str, source_id: str) -> pd.DataFrame:
    funcs = {
        "company_year": normalize_company_year,
        "names": normalize_names,
        "activities": normalize_activities,
        "addresses": normalize_addresses,
    }
    if kind not in funcs:
        raise ValueError(f"Tipo de fuente no soportado: {kind}")
    result = funcs[kind](df, source_id=source_id)
    result["source_payload_schema"] = json.dumps(sorted(df.columns.tolist()), ensure_ascii=False)
    return result
