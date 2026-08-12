from __future__ import annotations

import re

import pandas as pd


# Evaluate from the largest bands down so a substring such as "0,01 ... 200"
# cannot match inside "100.000,01 ... 200.000".
SALES_PATTERNS = [
    (r"MAS DE 1[.]?000[.]?000|1[.]?000[.]?000[,.]01", 12),
    (r"600[.]?000[,.]01.*1[.]?000[.]?000", 11),
    (r"200[.]?000[,.]01.*600[.]?000", 10),
    (r"100[.]?000[,.]01.*200[.]?000", 9),
    (r"50[.]?000[,.]01.*100[.]?000", 8),
    (r"25[.]?000[,.]01.*50[.]?000", 7),
    (r"10[.]?000[,.]01.*25[.]?000", 6),
    (r"5[.]?000[,.]01.*10[.]?000", 5),
    (r"2[.]?400[,.]01.*5[.]?000", 4),
    (r"600[,.]01.*2[.]?400", 3),
    (r"200[,.]01.*600", 2),
    (r"0[,.]01.*200", 1),
    (r"SIN (INFORMACION|VENTAS)", 0),
]


def sales_band_rank(text: object) -> int | None:
    value = str(text or "").upper()
    for pattern, rank in SALES_PATTERNS:
        if re.search(pattern, value):
            return rank
    return None


def enrich_company_year(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    out = df.copy()
    out["sales_band_rank"] = out["sales_band"].map(sales_band_rank).astype("Int64")
    out["workers_numeric"] = pd.to_numeric(out["workers"], errors="coerce").astype("Int64")
    start_year = pd.to_datetime(out["activity_start_date"], errors="coerce").dt.year
    out["entity_age_years"] = out["commercial_year"] - start_year
    out = out.sort_values(["entity_id", "commercial_year", "record_id"], na_position="last")
    out["prior_sales_band_rank"] = out.groupby("entity_id", dropna=False)["sales_band_rank"].shift(1).astype("Int64")
    out["sales_band_delta"] = (out["sales_band_rank"] - out["prior_sales_band_rank"]).astype("Int64")
    out["prior_region"] = out.groupby("entity_id", dropna=False)["region"].shift(1)
    out["region_changed"] = (out["prior_region"].fillna("") != "") & (out["prior_region"].fillna("") != out["region"].fillna(""))
    return out
