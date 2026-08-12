from __future__ import annotations

import re

import pandas as pd


# SII publica Tramo según ventas como código ordinal 1..13.
# Se mantiene fallback textual para reutilización/compatibilidad.
SALES_PATTERNS = [
    (r"MAS DE 1[.]?000[.]?000|MÁS DE 1[.]?000[.]?000|1[.]?000[.]?000[,.]01", 13),
    (r"600[.]?000[,.]01.*1[.]?000[.]?000", 12),
    (r"200[.]?000[,.]01.*600[.]?000", 11),
    (r"100[.]?000[,.]01.*200[.]?000", 10),
    (r"50[.]?000[,.]01.*100[.]?000", 9),
    (r"25[.]?000[,.]01.*50[.]?000", 8),
    (r"10[.]?000[,.]01.*25[.]?000", 7),
    (r"5[.]?000[,.]01.*10[.]?000", 6),
    (r"2[.]?400[,.]01.*5[.]?000", 5),
    (r"600[,.]01.*2[.]?400", 4),
    (r"200[,.]01.*600", 3),
    (r"0[,.]01.*200", 2),
    (r"SIN (INFORMACION|INFORMACIÓN|VENTAS)", 1),
]


def sales_band_rank(text: object) -> int | None:
    value = str(text or "").strip().upper()
    if re.fullmatch(r"(?:[1-9]|1[0-3])", value):
        return int(value)
    for pattern, rank in SALES_PATTERNS:
        if re.search(pattern, value):
            return rank
    return None


def enrich_company_year(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    out = df.copy()
    source_rank = out["sales_band_code"] if "sales_band_code" in out.columns else out["sales_band"]
    out["sales_band_rank"] = source_rank.map(sales_band_rank).astype("Int64")
    out["workers_numeric"] = pd.to_numeric(out["workers"], errors="coerce").astype("Int64")
    start_year = pd.to_datetime(out["activity_start_date"], errors="coerce").dt.year
    out["entity_age_years"] = out["commercial_year"] - start_year
    out = out.sort_values(["entity_id", "commercial_year", "record_id"], na_position="last")
    groups = out.groupby("entity_id", dropna=False)
    out["prior_sales_band_rank"] = groups["sales_band_rank"].shift(1).astype("Int64")
    raw_delta = out["sales_band_rank"] - out["prior_sales_band_rank"]
    known = (out["sales_band_rank"] > 1) & (out["prior_sales_band_rank"] > 1)
    out["sales_band_delta"] = raw_delta.where(known).astype("Int64")
    out["prior_workers_numeric"] = groups["workers_numeric"].shift(1).astype("Int64")
    out["workforce_ratio"] = out["workers_numeric"].astype("Float64") / out["prior_workers_numeric"].replace(0, pd.NA).astype("Float64")
    out["prior_region"] = groups["region"].shift(1)
    out["region_changed"] = (out["prior_region"].fillna("") != "") & (out["prior_region"].fillna("") != out["region"].fillna(""))
    if "main_activity" in out.columns:
        out["prior_main_activity"] = groups["main_activity"].shift(1)
        out["main_activity_changed"] = (
            out["prior_main_activity"].fillna("").str.strip().ne("")
            & out["main_activity"].fillna("").str.strip().ne("")
            & out["prior_main_activity"].fillna("").str.strip().ne(out["main_activity"].fillna("").str.strip())
        )
    else:
        out["prior_main_activity"] = ""
        out["main_activity_changed"] = False
    return out
