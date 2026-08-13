from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests

UAF_PAGE = "https://www.uaf.cl/es-cl/sujetos-obligados/sector-privado/inscritos-en-la-uaf"
SII_ACTIVITIES_PAGE = "https://www.sii.cl/sobre_el_sii/nominapersonasjuridicas.html"


def norm_text(value: object) -> str:
    text = str(value or "").strip().upper()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^A-Z0-9]+", " ", text).strip()


def normalize_rut(value: object) -> str:
    raw = re.sub(r"[^0-9Kk]", "", str(value or "")).upper()
    if len(raw) < 2:
        return ""
    return f"{raw[:-1].lstrip('0') or '0'}-{raw[-1]}"


def wilson_lower(successes: int, total: int, z: float = 1.96) -> float:
    if total <= 0:
        return 0.0
    p = successes / total
    den = 1 + z * z / total
    centre = p + z * z / (2 * total)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total)
    return max(0.0, (centre - margin) / den)


def discover_uaf_workbook(session: requests.Session) -> tuple[str, str, str]:
    r = session.get(UAF_PAGE, timeout=60)
    r.raise_for_status()
    html = r.text
    links = re.findall(r'href=["\']([^"\']+\.xlsx(?:\?[^"\']*)?)["\']', html, flags=re.I)
    if not links:
        raise RuntimeError("No se encontró XLSX de sujetos obligados en la página UAF")
    workbook_url = urljoin(UAF_PAGE, links[-1])
    cutoff = ""
    m = re.search(r"Lista\s+sujetos\s+obligados\s+inscritos\s+en\s+la\s+UAF\s+al\s+(\d{2}/\d{2}/\d{4})", html, flags=re.I)
    if m:
        d, mo, y = m.group(1).split("/")
        cutoff = f"{y}-{mo}-{d}"
    filename_date = ""
    fm = re.search(r"(?:al_)?(\d{2})[._-](\d{2})[._-](\d{4})", workbook_url)
    if fm:
        filename_date = f"{fm.group(3)}-{fm.group(2)}-{fm.group(1)}"
    return workbook_url, cutoff, filename_date


def parse_xlsx_first_sheet(content: bytes) -> pd.DataFrame:
    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root.findall("a:si", ns):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{ns['a']}}}t")))
        sheet = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))
        parsed_rows: list[dict[str, str]] = []
        for row in sheet.findall(".//a:sheetData/a:row", ns):
            out: dict[str, str] = {}
            for cell in row.findall("a:c", ns):
                ref = cell.attrib.get("r", "")
                mm = re.match(r"([A-Z]+)", ref)
                if not mm:
                    continue
                col = mm.group(1)
                typ = cell.attrib.get("t")
                value_node = cell.find("a:v", ns)
                value = "" if value_node is None else (value_node.text or "")
                if typ == "s" and value:
                    value = shared[int(value)]
                elif typ == "inlineStr":
                    inline = cell.find("a:is", ns)
                    value = "" if inline is None else "".join(t.text or "" for t in inline.iter(f"{{{ns['a']}}}t"))
                out[col] = value.strip()
            parsed_rows.append(out)
    if not parsed_rows:
        raise RuntimeError("XLSX UAF sin filas")
    header = parsed_rows[0]
    rows = []
    for raw in parsed_rows[1:]:
        rows.append({header.get(col, col): value for col, value in raw.items()})
    return pd.DataFrame(rows)


def load_uaf(session: requests.Session) -> tuple[pd.DataFrame, dict]:
    workbook_url, cutoff_displayed, filename_date = discover_uaf_workbook(session)
    r = session.get(workbook_url, timeout=90)
    r.raise_for_status()
    raw = parse_xlsx_first_sheet(r.content)
    cols = {norm_text(c): c for c in raw.columns}
    sector_col = next((orig for key, orig in cols.items() if "ACTIVIDAD ECONOMICA" in key), None)
    name_col = next((orig for key, orig in cols.items() if "PERSONA NATURAL O JURIDICA" in key), None)
    rut_col = next((orig for key, orig in cols.items() if "ROL UNICO TRIBUTARIO" in key), None)
    if not all((sector_col, name_col, rut_col)):
        raise RuntimeError(f"Columnas UAF no reconocidas: {list(raw.columns)}")
    df = pd.DataFrame(
        {
            "uaf_sector": raw[sector_col].fillna("").astype(str).str.strip(),
            "uaf_name": raw[name_col].fillna("").astype(str).str.strip(),
            "rut": raw[rut_col].map(normalize_rut),
        }
    )
    df = df[(df["rut"] != "") & (df["uaf_sector"] != "")].drop_duplicates("rut")
    meta = {
        "page_url": UAF_PAGE,
        "workbook_url": workbook_url,
        "cutoff_displayed": cutoff_displayed,
        "filename_date": filename_date,
        "cutoff_filename_mismatch": bool(cutoff_displayed and filename_date and cutoff_displayed != filename_date),
        "rows": int(len(df)),
        "sectors": int(df["uaf_sector"].nunique()),
    }
    return df, meta


def load_manual_crosswalk(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, sep=";", dtype=str).fillna("")
    if "sii_acteco" in df:
        df["sii_acteco"] = df["sii_acteco"].astype(str).str.strip()
    return df


def best_manual_sector(live_sector: str, manual_sectors: list[str]) -> tuple[str, float]:
    target = norm_text(live_sector)
    best, score = "", 0.0
    target_tokens = set(target.split())
    for candidate in manual_sectors:
        c = norm_text(candidate)
        seq = SequenceMatcher(None, target, c).ratio()
        tokens = set(c.split())
        jaccard = len(target_tokens & tokens) / max(1, len(target_tokens | tokens))
        combined = 0.65 * seq + 0.35 * jaccard
        if combined > score:
            best, score = candidate, combined
    return best, score


def classify_role(n_sector: int, support: int, coverage: float, lift: float, manual: bool) -> tuple[str, str]:
    if n_sector >= 10 and coverage >= 0.60 and lift >= 3:
        return "GATILLANTE_EMPIRICO_ALTO", "ALTA"
    if n_sector >= 5 and coverage >= 0.30 and lift >= 2:
        return "GATILLANTE_EMPIRICO_MEDIO", "MEDIA_ALTA"
    if manual and coverage >= 0.15 and support >= 2:
        return "GATILLANTE_NORMATIVO_CON_RESPALDO", "MEDIA"
    if n_sector < 5 and support >= 1:
        return "EVIDENCIA_LIMITADA_POR_MUESTRA", "BAJA_MUESTRA"
    if coverage >= 0.10 and support >= 2:
        return "ACTIVIDAD_COMPLEMENTARIA", "MEDIA_BAJA"
    return "ACTIVIDAD_INCIDENTAL", "BAJA"


def false_positive_risk(sii_code_entities: int, uaf_any_with_code: int) -> str:
    if sii_code_entities <= 0:
        return "NO_EVALUABLE"
    rate = uaf_any_with_code / sii_code_entities
    if rate >= 0.20 or sii_code_entities <= max(10, 2 * uaf_any_with_code):
        return "BAJO"
    if rate >= 0.03:
        return "MEDIO"
    return "ALTO"


def build_empirical(uaf: pd.DataFrame, acts: pd.DataFrame, manual: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    acts = acts.copy()
    acts["rut"] = acts["rut"].fillna("").astype(str).map(normalize_rut)
    acts["activity_code"] = acts["activity_code"].fillna("").astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    acts["activity_name"] = acts["activity_name"].fillna("").astype(str).str.strip()
    acts = acts[(acts["rut"] != "") & (acts["activity_code"] != "")]
    acts = acts.drop_duplicates(["rut", "activity_code"])

    code_totals = acts.groupby("activity_code")["rut"].nunique().to_dict()
    glosas = (
        acts.groupby("activity_code")["activity_name"]
        .agg(lambda s: Counter(x for x in s if x).most_common(1)[0][0] if any(bool(x) for x in s) else "")
        .to_dict()
    )
    uaf_ruts = set(uaf["rut"])
    uaf_acts = acts[acts["rut"].isin(uaf_ruts)].copy()
    matched_uaf_ruts = set(uaf_acts["rut"])
    n_all_matched = len(matched_uaf_ruts)
    uaf_any_code = uaf_acts.groupby("activity_code")["rut"].nunique().to_dict()

    manual_sectors = sorted(manual["uaf_sector"].dropna().astype(str).unique().tolist()) if not manual.empty else []
    manual_map: dict[str, tuple[str, float, set[str]]] = {}
    for live in sorted(uaf["uaf_sector"].unique()):
        best, sim = best_manual_sector(live, manual_sectors) if manual_sectors else ("", 0.0)
        codes = set(manual.loc[manual["uaf_sector"] == best, "sii_acteco"].astype(str)) if best else set()
        manual_map[live] = (best, sim, {c for c in codes if c})

    detail_rows: list[dict] = []
    sector_stats: list[dict] = []
    for sector, sector_df in uaf.groupby("uaf_sector"):
        sector_ruts = set(sector_df["rut"])
        matched = sector_ruts & matched_uaf_ruts
        n_sector_total = len(sector_ruts)
        n_sector = len(matched)
        best_manual, manual_similarity, manual_codes = manual_map.get(sector, ("", 0.0, set()))
        sub = uaf_acts[uaf_acts["rut"].isin(matched)]
        support_by_code = sub.groupby("activity_code")["rut"].nunique().to_dict()
        for code, support in support_by_code.items():
            d = int(code_totals.get(code, 0))
            b = int(uaf_any_code.get(code, 0))
            coverage = support / n_sector if n_sector else 0.0
            purity = support / b if b else 0.0
            code_uaf_rate = b / d if d else 0.0
            sector_reg_rate = support / d if d else 0.0
            baseline = b / n_all_matched if n_all_matched else 0.0
            lift = coverage / baseline if baseline else 0.0
            manual_support = bool(code in manual_codes and manual_similarity >= 0.45)
            lower = wilson_lower(support, n_sector)
            lift_component = min(1.0, math.log1p(max(lift, 0.0)) / math.log(11))
            score = 100 * (0.45 * lower + 0.20 * lift_component + 0.15 * purity + 0.20 * (1.0 if manual_support else 0.0))
            role, confidence = classify_role(n_sector, support, coverage, lift, manual_support)
            detail_rows.append(
                {
                    "uaf_sector": sector,
                    "uaf_ruts_total": n_sector_total,
                    "uaf_ruts_match_sii_pj": n_sector,
                    "uaf_match_rate_sii_pj": round(n_sector / n_sector_total, 6) if n_sector_total else 0,
                    "sii_acteco": code,
                    "sii_glosa": glosas.get(code, ""),
                    "support_uaf_sector": int(support),
                    "coverage_sector": round(coverage, 6),
                    "coverage_wilson_low": round(lower, 6),
                    "uaf_code_purity": round(purity, 6),
                    "lift_vs_uaf": round(lift, 4),
                    "sii_ruts_with_code": d,
                    "uaf_registered_any_with_code": b,
                    "registered_rate_any_uaf": round(code_uaf_rate, 6),
                    "registered_rate_target_sector": round(sector_reg_rate, 6),
                    "universe_sii_not_uaf_with_code": max(0, d - b),
                    "manual_sector_prior": best_manual,
                    "manual_sector_similarity": round(manual_similarity, 4),
                    "manual_code_prior": "SI" if manual_support else "NO",
                    "empirical_role": role,
                    "confidence": confidence,
                    "false_positive_risk": false_positive_risk(d, b),
                    "empirical_score": round(score, 2),
                }
            )
        sector_stats.append(
            {
                "uaf_sector": sector,
                "uaf_ruts_total": n_sector_total,
                "uaf_ruts_match_sii_pj": n_sector,
                "uaf_match_rate_sii_pj": round(n_sector / n_sector_total, 6) if n_sector_total else 0,
                "manual_sector_prior": best_manual,
                "manual_sector_similarity": round(manual_similarity, 4),
            }
        )

    detail = pd.DataFrame(detail_rows)
    if detail.empty:
        return detail, pd.DataFrame(sector_stats), {}
    detail = detail.sort_values(["uaf_sector", "empirical_score", "support_uaf_sector"], ascending=[True, False, False])
    detail["rank_sector"] = detail.groupby("uaf_sector").cumcount() + 1

    selected_parts = []
    for sector, group in detail.groupby("uaf_sector", sort=False):
        n = int(group["uaf_ruts_match_sii_pj"].iloc[0])
        min_support = max(2, math.ceil(0.02 * n)) if n >= 5 else 1
        keep = group[
            ((group["rank_sector"] <= 8) & (group["support_uaf_sector"] >= min_support))
            | (group["manual_code_prior"] == "SI")
            | group["empirical_role"].str.startswith("GATILLANTE_")
        ].copy()
        selected_parts.append(keep)
    selected = pd.concat(selected_parts, ignore_index=True) if selected_parts else detail.head(0)
    selected = selected.sort_values(["uaf_sector", "empirical_score"], ascending=[True, False])

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "uaf_rows": int(len(uaf)),
        "uaf_sectors": int(uaf["uaf_sector"].nunique()),
        "uaf_ruts_matched_sii_pj": int(len(matched_uaf_ruts)),
        "uaf_ruts_without_match_sii_pj": int(len(uaf_ruts - matched_uaf_ruts)),
        "sii_pj_ruts_with_activities": int(acts["rut"].nunique()),
        "sii_distinct_activity_codes": int(acts["activity_code"].nunique()),
        "selected_crosswalk_rows": int(len(selected)),
    }
    return selected, pd.DataFrame(sector_stats), summary


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--activities-parquet", required=True)
    p.add_argument("--manual-crosswalk", default="config/uaf_sii_crosswalk.csv")
    p.add_argument("--output-csv", default="config/uaf_sii_crosswalk_v2.csv")
    p.add_argument("--summary-json", default="docs/data/uaf_sii_empirical_summary.json")
    p.add_argument("--sector-csv", default="docs/data/uaf_sii_empirical_sector_coverage.csv")
    args = p.parse_args()

    session = requests.Session()
    session.headers.update({"User-Agent": "Radar-SII-UAF-Empirical/0.2 (+GitHub Actions; OSINT)"})
    uaf, uaf_meta = load_uaf(session)
    acts = pd.read_parquet(args.activities_parquet, columns=["rut", "activity_code", "activity_name"])
    manual = load_manual_crosswalk(Path(args.manual_crosswalk))
    selected, sectors, summary = build_empirical(uaf, acts, manual)

    out = Path(args.output_csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    selected.to_csv(out, sep=";", index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)
    sec = Path(args.sector_csv)
    sec.parent.mkdir(parents=True, exist_ok=True)
    sectors.sort_values("uaf_sector").to_csv(sec, sep=";", index=False, encoding="utf-8-sig")

    payload = {
        **summary,
        "method": {
            "unit": "RUT",
            "uaf_sector_source": "Registro de Entidades Reportantes UAF",
            "sii_activity_source": "Nómina de actividades económicas vigentes de personas jurídicas SII",
            "interpretation": "La actividad SII es evidencia de screening y no prueba por sí sola la calidad jurídica de sujeto obligado.",
            "gatillante_definition": "Código ACTECO recurrente y enriquecido empíricamente dentro de un sector UAF; se separa de actividades complementarias y códigos amplios.",
        },
        "sources": {
            "uaf": uaf_meta,
            "sii": {
                "official_page": SII_ACTIVITIES_PAGE,
                "published_update": "2026-05",
                "dataset": "PUB_NOM_ACTECOS.zip",
            },
        },
    }
    summary_path = Path(args.summary_json)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
