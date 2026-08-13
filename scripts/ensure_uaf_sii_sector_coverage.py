from __future__ import annotations

import argparse
import csv
from pathlib import Path

import pandas as pd


def text(value: object) -> str:
    return str(value or "").strip()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--policy", default="config/uaf_sii_screening_policy.csv")
    p.add_argument("--coverage", default="docs/data/uaf_sii_empirical_sector_coverage.csv")
    p.add_argument("--manual", default="config/uaf_sii_crosswalk.csv")
    args = p.parse_args()

    policy = pd.read_csv(args.policy, sep=";", dtype=str).fillna("")
    coverage = pd.read_csv(args.coverage, sep=";", dtype=str).fillna("")
    manual = pd.read_csv(args.manual, sep=";", dtype=str).fillna("")

    present = set(policy["uaf_sector"].astype(str))
    rows: list[dict[str, str]] = []
    for _, cov in coverage.iterrows():
        sector = text(cov.get("uaf_sector"))
        if not sector or sector in present:
            continue
        prior = text(cov.get("manual_sector_prior"))
        m = manual[manual["uaf_sector"].astype(str) == prior]
        codes = ",".join(sorted({text(x) for x in m.get("sii_acteco", pd.Series(dtype=str)) if text(x)}))
        sources = " / ".join(sorted({text(x) for x in m.get("fuente_complementaria_sugerida", pd.Series(dtype=str)) if text(x)}))
        row = {col: "" for col in policy.columns}
        row.update({
            "uaf_sector": sector,
            "uaf_ruts_total": text(cov.get("uaf_ruts_total")),
            "uaf_ruts_match_sii_pj": text(cov.get("uaf_ruts_match_sii_pj")),
            "uaf_match_rate_sii_pj": text(cov.get("uaf_match_rate_sii_pj")),
            "manual_sector_prior": prior,
            "manual_sector_similarity": text(cov.get("manual_sector_similarity")),
            "manual_code_prior": "REFERENCIA_SIN_MATCH_EMPIRICO",
            "empirical_role": "SIN_MATCH_EN_NOMINA_SII_PJ",
            "confidence": "NO_EVALUABLE",
            "false_positive_risk": "NO_EVALUABLE",
            "tipo_equivalencia": "REFERENCIA_NORMATIVA_SIN_EVIDENCIA_EMPIRICA_PJ",
            "fuente_complementaria": sources,
            "screening_class": "NO_EVALUABLE_CON_NOMINA_SII_PJ",
            "candidate_use": "NO",
            "screening_priority": "D",
            "legal_interpretation": "El registro UAF del sector no presenta RUT emparejados en la nómina pública SII de actividades de personas jurídicas. No debe inferirse un universo de potenciales sujetos obligados desde ACTECO; usar registro sectorial o fuente específica.",
            "candidate_universe_gross": "",
            "candidate_universe_note": f"Códigos ACTECO de referencia normativa previa: {codes or 'sin código directo'}. No se usan para generar candidatos sin validación sectorial.",
        })
        rows.append(row)

    if rows:
        policy = pd.concat([policy, pd.DataFrame(rows)], ignore_index=True, sort=False)
    order = {"A": 0, "A_REGISTRO": 0, "B": 1, "C": 2, "D": 3}
    policy["_priority"] = policy["screening_priority"].map(order).fillna(9)
    policy["_score"] = pd.to_numeric(policy.get("empirical_score", ""), errors="coerce").fillna(-1)
    policy = policy.sort_values(["uaf_sector", "_priority", "_score"], ascending=[True, True, False]).drop(columns=["_priority", "_score"])

    target = Path(args.policy)
    policy.to_csv(target, sep=";", index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)
    expected = set(coverage["uaf_sector"].astype(str))
    observed = set(policy["uaf_sector"].astype(str))
    missing = sorted(expected - observed)
    if missing:
        raise RuntimeError(f"Sectores UAF ausentes de la política: {missing}")
    print(f"uaf_sectors_covered={len(observed)} expected={len(expected)} appended={len(rows)}")


if __name__ == "__main__":
    main()
