from __future__ import annotations

import argparse
import csv
from pathlib import Path

import pandas as pd


def _text(value: object) -> str:
    return str(value or "").strip()


def _num(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _manual_lookup(manual: pd.DataFrame) -> dict[tuple[str, str], dict[str, str]]:
    out: dict[tuple[str, str], dict[str, str]] = {}
    for _, row in manual.fillna("").iterrows():
        sector = _text(row.get("uaf_sector"))
        code = _text(row.get("sii_acteco"))
        out[(sector, code)] = {
            "tipo_equivalencia": _text(row.get("tipo_equivalencia")),
            "confianza_manual": _text(row.get("confianza")),
            "uso_radar_manual": _text(row.get("uso_radar")),
            "fuente_complementaria": _text(row.get("fuente_complementaria_sugerida")),
        }
    return out


def classify(row: pd.Series, manual_meta: dict[str, str]) -> tuple[str, str, str, str]:
    n = int(_num(row.get("uaf_ruts_match_sii_pj")))
    total = int(_num(row.get("uaf_ruts_total")))
    support = int(_num(row.get("support_uaf_sector")))
    coverage = _num(row.get("coverage_sector"))
    match_rate = _num(row.get("uaf_match_rate_sii_pj"))
    fp = _text(row.get("false_positive_risk"))
    empirical = _text(row.get("empirical_role"))
    use = manual_meta.get("uso_radar_manual", "")
    equivalence = manual_meta.get("tipo_equivalencia", "")
    confidence = manual_meta.get("confianza_manual", "")

    if total and match_rate < 0.10:
        return (
            "NO_EVALUABLE_CON_NOMINA_SII_PJ",
            "NO",
            "D",
            "La cobertura del sector UAF en la nómina pública SII de personas jurídicas es insuficiente; no inferir obligación desde ACTECO.",
        )

    if use == "MATCH_FUERTE" and confidence == "ALTA":
        if support >= 2 and coverage >= 0.15:
            return (
                "ACTECO_PRIORITARIO_RESPALDADO",
                "SI",
                "A",
                "Equivalencia normativa fuerte y presencia empírica en RUT inscritos UAF; apto para generar candidatos, sujeto a validación de condición regulatoria cuando corresponda.",
            )
        if support >= 1 and n < 5:
            return (
                "ACTECO_PRIORITARIO_MUESTRA_BAJA",
                "REVISAR",
                "B",
                "Equivalencia normativa fuerte, pero la muestra UAF emparejada es pequeña; usar como señal prioritaria con validación externa.",
            )
        return (
            "ACTECO_NORMATIVO_SIN_RESPALDO_EMPIRICO_SUFFICIENTE",
            "REVISAR",
            "C",
            "La tabla normativa lo considera fuerte, pero el cruce empírico actual no alcanza soporte suficiente.",
        )

    if use == "CANDIDATO":
        if support >= 3 and coverage >= 0.20:
            return (
                "ACTECO_CANDIDATO_RESPALDADO",
                "REVISAR",
                "B",
                "Código parcial/candidato respaldado por recurrencia empírica; puede generar candidatos secundarios, nunca concluir SO por sí solo.",
            )
        return (
            "ACTECO_CANDIDATO_DEBIL",
            "NO_SOLO",
            "C",
            "Código parcial con evidencia insuficiente; usar únicamente junto con otras señales o registros sectoriales.",
        )

    if use == "SOLO_PRESELECCION":
        return (
            "ACTECO_AMPLIO_SOLO_CONTEXTO",
            "NO_SOLO",
            "D",
            "ACTECO demasiado amplio para sostener una hipótesis de sujeto obligado sin evidencia adicional.",
        )

    if empirical.startswith("GATILLANTE_EMPIRICO"):
        if coverage >= 0.60 and support >= 5 and fp in {"BAJO", "MEDIO"}:
            return (
                "FIRMA_EMPIRICA_FUERTE_NO_CAUSAL",
                "COMPLEMENTARIO",
                "B",
                "Actividad muy recurrente entre inscritos del sector, pero no identificada como equivalencia normativa fuerte; úsese para ranking, no como gatillante jurídico único.",
            )
        return (
            "FIRMA_EMPIRICA_AMPLIA_NO_CAUSAL",
            "NO_SOLO",
            "C",
            "Asociación empírica relevante, pero amplia o poco específica; útil como característica de modelo, no como gatillante jurídico.",
        )

    if empirical == "EVIDENCIA_LIMITADA_POR_MUESTRA":
        return (
            "MUESTRA_EMPIRICA_LIMITADA",
            "NO_SOLO",
            "D",
            "La muestra disponible es demasiado pequeña para inferir una regla generalizable.",
        )

    return (
        "ACTIVIDAD_COMPLEMENTARIA_O_INCIDENTAL",
        "NO",
        "D",
        "No debe utilizarse para generar candidatos por sí sola.",
    )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--empirical", default="config/uaf_sii_crosswalk_v2.csv")
    p.add_argument("--manual", default="config/uaf_sii_crosswalk.csv")
    p.add_argument("--sector-coverage", default="docs/data/uaf_sii_empirical_sector_coverage.csv")
    p.add_argument("--output", default="config/uaf_sii_screening_policy.csv")
    args = p.parse_args()

    empirical = pd.read_csv(args.empirical, sep=";", dtype=str).fillna("")
    manual = pd.read_csv(args.manual, sep=";", dtype=str).fillna("")
    coverage = pd.read_csv(args.sector_coverage, sep=";", dtype=str).fillna("")
    lookup = _manual_lookup(manual)

    enriched_rows: list[dict] = []
    for _, row in empirical.iterrows():
        base = row.to_dict()
        key = (_text(row.get("manual_sector_prior")), _text(row.get("sii_acteco")))
        meta = lookup.get(key, {
            "tipo_equivalencia": "",
            "confianza_manual": "",
            "uso_radar_manual": "",
            "fuente_complementaria": "",
        })
        screening_class, candidate_use, priority, interpretation = classify(row, meta)
        base.update(meta)
        base.update({
            "screening_class": screening_class,
            "candidate_use": candidate_use,
            "screening_priority": priority,
            "legal_interpretation": interpretation,
            "candidate_universe_gross": _text(row.get("universe_sii_not_uaf_with_code")),
            "candidate_universe_note": "Universo bruto SII con ACTECO menos RUT inscritos UAF en cualquier sector; no equivale a incumplimiento ni a sujeto obligado confirmado.",
        })
        enriched_rows.append(base)

    existing_live = set(empirical["uaf_sector"].astype(str))
    for _, cov in coverage.iterrows():
        live = _text(cov.get("uaf_sector"))
        manual_sector = _text(cov.get("manual_sector_prior"))
        ext_rows = manual[
            (manual["uaf_sector"].astype(str) == manual_sector)
            & (manual["uso_radar"].astype(str) == "REQUIERE_REGISTRO_EXTERNO")
        ]
        if ext_rows.empty:
            continue
        source = " / ".join(sorted({x for x in ext_rows["fuente_complementaria_sugerida"].astype(str) if x}))
        enriched_rows.append({
            "uaf_sector": live,
            "uaf_ruts_total": _text(cov.get("uaf_ruts_total")),
            "uaf_ruts_match_sii_pj": _text(cov.get("uaf_ruts_match_sii_pj")),
            "uaf_match_rate_sii_pj": _text(cov.get("uaf_match_rate_sii_pj")),
            "sii_acteco": "",
            "sii_glosa": "",
            "support_uaf_sector": "",
            "coverage_sector": "",
            "coverage_wilson_low": "",
            "uaf_code_purity": "",
            "lift_vs_uaf": "",
            "sii_ruts_with_code": "",
            "uaf_registered_any_with_code": "",
            "registered_rate_any_uaf": "",
            "registered_rate_target_sector": "",
            "universe_sii_not_uaf_with_code": "",
            "manual_sector_prior": manual_sector,
            "manual_sector_similarity": _text(cov.get("manual_sector_similarity")),
            "manual_code_prior": "SI_SIN_ACTECO",
            "empirical_role": "CONDICION_NO_REPRESENTABLE_POR_ACTECO",
            "confidence": "ALTA_EN_LIMITACION",
            "false_positive_risk": "NO_APLICA",
            "empirical_score": "",
            "rank_sector": "",
            "tipo_equivalencia": "SIN_ACTECO_DIRECTO",
            "confianza_manual": "BAJA",
            "uso_radar_manual": "REQUIERE_REGISTRO_EXTERNO",
            "fuente_complementaria": source,
            "screening_class": "REGISTRO_EXTERNO_REQUERIDO",
            "candidate_use": "NO_SOLO_ACTECO",
            "screening_priority": "A_REGISTRO",
            "legal_interpretation": "La condición de sujeto obligado depende de una calidad jurídica, autorización, fiscalización o registro sectorial; ACTECO SII no es suficiente.",
            "candidate_universe_gross": "",
            "candidate_universe_note": "Construir el universo desde el registro sectorial correspondiente y luego contrastar contra UAF.",
        })

    out = pd.DataFrame(enriched_rows)
    rank_order = {"A": 0, "A_REGISTRO": 0, "B": 1, "C": 2, "D": 3}
    out["_p"] = out["screening_priority"].map(rank_order).fillna(9)
    out["_score"] = pd.to_numeric(out.get("empirical_score", ""), errors="coerce").fillna(-1)
    out = out.sort_values(["uaf_sector", "_p", "_score"], ascending=[True, True, False]).drop(columns=["_p", "_score"])

    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(target, sep=";", index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)

    print("screening_rows=", len(out))
    print(out["screening_class"].value_counts().to_string())
    print("candidate_use=")
    print(out["candidate_use"].value_counts().to_string())


if __name__ == "__main__":
    main()
