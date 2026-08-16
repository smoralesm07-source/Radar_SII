"""Resolución territorial del SII contra el índice canónico del Context Hub."""

import pandas as pd

from radar_sii.normalize import _add_canonical_territory
from radar_sii.territory import match_key, resolve

# Glosas tal como las publica el SII en la nómina de personas jurídicas.
SAMPLE = pd.DataFrame(
    [
        ("XIII REGION METROPOLITANA", "Santiago", "LAS CONDES"),
        ("IV REGION COQUIMBO", "Limarí", "OVALLE"),
    ],
    columns=["region", "province", "commune"],
)


def test_compound_region_gloss_resolves():
    """El SII publica «numeral romano + REGION + nombre» en un solo campo."""
    assert resolve("XIII REGION METROPOLITANA", "REGION") == ("CL-REG-13", "VALIDATED_COMPOUND")
    assert resolve("IV REGION COQUIMBO", "REGION") == ("CL-REG-04", "VALIDATED_COMPOUND")


def test_compound_requires_both_signals_to_agree():
    """Numeral y nombre son señales independientes: si discrepan no se elige."""
    assert resolve("IV REGION METROPOLITANA", "REGION") == (None, "CONFLICTING_SIGNALS")


def test_province_and_commune_resolve():
    assert resolve("Santiago", "PROVINCE") == ("CL-PROV-131", "VALIDATED_EXACT")
    assert resolve("Limarí", "PROVINCE") == ("CL-PROV-043", "VALIDATED_EXACT")
    assert resolve("LAS CONDES", "COMMUNE") == ("CL-COM-13114", "VALIDATED_EXACT")
    assert resolve("OVALLE", "COMMUNE") == ("CL-COM-04301", "VALIDATED_EXACT")


def test_level_matters_for_shared_names():
    """«Santiago» es provincia y comuna a la vez; el nivel decide."""
    assert resolve("Santiago", "PROVINCE")[0] == "CL-PROV-131"
    assert resolve("Santiago", "COMMUNE")[0] == "CL-COM-13101"


def test_normalize_adds_canonical_columns_without_touching_the_source():
    df = SAMPLE.copy()
    _add_canonical_territory(df)
    # La glosa original se conserva intacta.
    assert list(df["region"]) == list(SAMPLE["region"])
    assert list(df["region_territory_id"]) == ["CL-REG-13", "CL-REG-04"]
    assert list(df["province_territory_id"]) == ["CL-PROV-131", "CL-PROV-043"]
    assert list(df["commune_territory_id"]) == ["CL-COM-13114", "CL-COM-04301"]


def test_commune_is_cross_checked_against_declared_region():
    df = SAMPLE.copy()
    _add_canonical_territory(df)
    assert list(df["territory_coherence"]) == ["COHERENT", "COHERENT"]


def test_incoherent_row_is_flagged_not_corrected():
    """Una comuna que no pertenece a la región declarada es defecto del origen."""
    df = pd.DataFrame([("IV REGION COQUIMBO", "Santiago", "LAS CONDES")],
                      columns=["region", "province", "commune"])
    _add_canonical_territory(df)
    assert df["territory_coherence"].iloc[0] == "REGION_COMMUNE_MISMATCH"
    # Ninguna de las dos claves se descarta ni se ajusta: se marca y se conserva.
    assert df["region_territory_id"].iloc[0] == "CL-REG-04"
    assert df["commune_territory_id"].iloc[0] == "CL-COM-13114"


def test_unresolved_stays_null_with_explicit_status():
    df = pd.DataFrame([("Region Inventada", "", "COMUNA QUE NO EXISTE")],
                      columns=["region", "province", "commune"])
    _add_canonical_territory(df)
    assert df["region_territory_id"].iloc[0] is None
    assert df["region_mapping_status"].iloc[0] == "UNRESOLVED_NAME_ONLY"
    assert df["province_mapping_status"].iloc[0] == "UNKNOWN"
    assert df["territory_coherence"].iloc[0] == "NOT_EVALUABLE"


def test_no_fuzzy_promotion():
    for text in ("LAS CONDE", "Ovall", "Metropolit"):
        assert resolve(text, "COMMUNE")[0] is None


def test_key_recipe_matches_the_hub():
    assert match_key("LAS CONDES") == "LASCONDES"
    assert match_key("Limarí") == "LIMARI"
