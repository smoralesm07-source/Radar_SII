from __future__ import annotations

from pathlib import Path

import pandas as pd

DEFAULT_REGISTRY = Path("config/public_entities_registry.csv")
PUBLIC_COLUMNS = [
    "public_entity_id",
    "official_name",
    "is_public_entity",
    "is_public_service_strict",
    "public_entity_type",
    "source_system",
    "source_code",
    "chilecompra_reference_match",
    "datos_gob_reference_match",
    "gob_cl_reference_match",
    "dipres_reference_match",
    "sii_match_method",
    "sii_match_confidence",
]


def load_public_master(path: Path = DEFAULT_REGISTRY) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, sep=";", dtype=str).fillna("")


def load_public_registry(path: Path = DEFAULT_REGISTRY) -> pd.DataFrame:
    df = load_public_master(path)
    if df.empty or "entity_id" not in df.columns:
        return pd.DataFrame(columns=["entity_id", *PUBLIC_COLUMNS])
    cols = ["entity_id", *[c for c in PUBLIC_COLUMNS if c in df.columns]]
    df = df.loc[df["entity_id"].astype(str).ne(""), cols].copy()
    if df.empty:
        return df
    agg: dict[str, object] = {}
    bool_cols = {
        "is_public_entity", "is_public_service_strict", "chilecompra_reference_match",
        "datos_gob_reference_match", "gob_cl_reference_match", "dipres_reference_match",
    }
    for c in cols:
        if c == "entity_id":
            continue
        if c in bool_cols:
            agg[c] = lambda s: "true" if any(str(x).lower() == "true" for x in s) else "false"
        else:
            agg[c] = lambda s: " | ".join(sorted({str(x) for x in s if str(x)}))
    return df.groupby("entity_id", as_index=False).agg(agg)


def enrich_public_entities(df: pd.DataFrame, path: Path = DEFAULT_REGISTRY) -> pd.DataFrame:
    result = df.copy()
    if "entity_id" not in result.columns:
        return result

    derived_context = {
        "public_entity_id", "public_entity_name", "is_public_entity", "is_public_service_strict",
        "public_entity_type", "source_system", "source_code", "chilecompra_reference_match",
        "datos_gob_reference_match", "gob_cl_reference_match", "dipres_reference_match",
        "sii_match_method", "sii_match_confidence", "public_entity_source_system",
        "public_entity_source_code",
    }
    result = result.drop(columns=[c for c in derived_context if c in result.columns], errors="ignore")

    registry = load_public_registry(path)
    if registry.empty:
        result["is_public_entity"] = False
        result["is_public_service_strict"] = False
        result["public_entity_type"] = ""
        result["public_entity_name"] = ""
    else:
        registry = registry.rename(columns={"official_name": "public_entity_name"})
        result = result.merge(registry, how="left", on="entity_id", validate="many_to_one")
        for col in (
            "is_public_entity", "is_public_service_strict", "chilecompra_reference_match",
            "datos_gob_reference_match", "gob_cl_reference_match", "dipres_reference_match",
        ):
            if col in result.columns:
                result[col] = result[col].fillna("false").astype(str).str.lower().eq("true")
        for col in result.columns:
            if col.startswith("public_") or col in {"source_system", "source_code", "sii_match_method", "sii_match_confidence"}:
                if result[col].dtype == object:
                    result[col] = result[col].fillna("")

    if "analysis_population" in result.columns:
        result["analysis_population"] = result["is_public_entity"].map(
            {True: "PUBLIC_ENTITY_CONTEXT", False: "PRIVATE_OR_OTHER_ENTITY"}
        )
    if "business_ranking_eligible" in result.columns:
        result["business_ranking_eligible"] = ~result["is_public_entity"].astype(bool)
    if "signal_applicability" in result.columns:
        result["signal_applicability"] = result["is_public_entity"].map(
            {True: "CONTEXT_ONLY_PUBLIC_ENTITY", False: "STANDARD_BUSINESS_SIGNAL"}
        )
    return result


def apply_public_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    result = df
    bool_filters = {
        "is_public_entity": "is_public_entity",
        "is_public_service_strict": "is_public_service_strict",
    }
    for key, col in bool_filters.items():
        if key not in filters or col not in result.columns or filters[key] in (None, ""):
            continue
        value = filters[key]
        if isinstance(value, bool):
            expected = value
        else:
            expected = str(value).strip().lower() in {"1", "true", "si", "sí", "yes"}
        if result[col].dtype == bool:
            flag = result[col]
        else:
            flag = result[col].fillna("false").astype(str).str.lower().eq("true")
        result = result[flag == expected]
    if filters.get("public_entity_type") not in (None, "") and "public_entity_type" in result.columns:
        expected = str(filters["public_entity_type"])
        result = result[result["public_entity_type"].astype(str).str.contains(expected, case=False, regex=False)]
    return result
