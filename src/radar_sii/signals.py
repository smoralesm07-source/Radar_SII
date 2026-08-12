from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from .ids import deterministic_id

SEVERITY_SCORE = {"LOW": 25, "MEDIUM": 50, "HIGH": 75}


def _signal(entity_id: str, signal_type: str, period: str, severity: str, confidence: str, why: str, checks: list[str], source_record_id: str = "") -> dict:
    return {
        "signal_id": deterministic_id("SII-SIG", entity_id, signal_type, period, source_record_id),
        "entity_id": entity_id,
        "signal_type": signal_type,
        "period": period,
        "severity": severity,
        "severity_score": SEVERITY_SCORE[severity],
        "confidence": confidence,
        "why_flagged": why,
        "recommended_checks": checks,
        "source_record_id": source_record_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def signals_from_company_year(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for r in df.itertuples(index=False):
        eid = getattr(r, "entity_id", None)
        year = getattr(r, "commercial_year", None)
        if not eid or pd.isna(year):
            continue
        period = str(int(year))
        rank = getattr(r, "sales_band_rank", None)
        workers = getattr(r, "workers_numeric", None)
        age = getattr(r, "entity_age_years", None)
        delta = getattr(r, "sales_band_delta", None)
        record_id = getattr(r, "record_id", "") or ""
        if pd.notna(delta) and int(delta) >= 3:
            rows.append(_signal(eid, "SALES_BAND_JUMP", period, "MEDIUM", "HIGH", f"El tramo de ventas aumentó {int(delta)} niveles respecto del año anterior publicado.", ["Revisar continuidad de actividad, cambios de giro y contrapartes públicas/privadas disponibles en otros radares.", "Comparar con pares del mismo rubro y región."], record_id))
        if pd.notna(rank) and int(rank) >= 9 and pd.notna(workers) and int(workers) <= 2:
            rows.append(_signal(eid, "HIGH_SALES_LOW_WORKFORCE", period, "MEDIUM", "MEDIUM", f"Tramo de ventas alto (nivel {int(rank)}) con {int(workers)} trabajadores dependientes informados.", ["Contextualizar por industria y modelo operativo; no todas las actividades requieren dotaciones altas.", "Revisar evolución interanual de trabajadores, actividades y domicilios."], record_id))
        if pd.notna(rank) and int(rank) >= 9 and pd.notna(age) and 0 <= int(age) <= 2:
            rows.append(_signal(eid, "RECENT_START_HIGH_SALES", period, "MEDIUM", "MEDIUM", f"Empresa con hasta {int(age)} años desde el inicio publicado y tramo de ventas alto.", ["Validar historia societaria en fuentes abiertas complementarias.", "Cruzar con contratación pública y hallazgos CGR cuando corresponda."], record_id))
        neg = str(getattr(r, "negative_equity_band", "") or "").strip()
        if pd.notna(rank) and int(rank) >= 9 and neg and neg.lower() not in {"nan", "0", "sin informacion", "sin información"}:
            rows.append(_signal(eid, "HIGH_SALES_NEGATIVE_EQUITY", period, "MEDIUM", "MEDIUM", "Tramo de ventas alto coexistiendo con tramo de capital propio tributario negativo informado por la fuente.", ["Revisar persistencia del patrón en varios años.", "No inferir insolvencia ni ilicitud: el dato es tributario y requiere contexto financiero adicional."], record_id))
        if bool(getattr(r, "region_changed", False)):
            rows.append(_signal(eid, "REGION_CHANGE", period, "LOW", "HIGH", "La región informada para la empresa cambió respecto del año comercial anterior.", ["Contrastar con el historial de direcciones publicado por SII.", "Determinar si el cambio coincide con cambios de actividad o crecimiento."], record_id))
    return pd.DataFrame(rows)


def signals_from_current(names: pd.DataFrame, activities: pd.DataFrame, addresses: pd.DataFrame, company_year: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    if not activities.empty:
        counts = activities.dropna(subset=["entity_id"]).groupby("entity_id")["activity_record_id"].nunique()
        for eid, count in counts.items():
            if count >= 6:
                rows.append(_signal(eid, "ACTIVITY_BREADTH", "CURRENT", "LOW", "HIGH", f"Registra {int(count)} actividades económicas vigentes/publicadas.", ["Revisar coherencia económica entre actividades y evolución histórica.", "No tratar diversidad de giros como irregularidad por sí sola."]))
    if not addresses.empty:
        g = addresses.dropna(subset=["entity_id"]).groupby("entity_id").agg(address_count=("address_record_id", "nunique"), region_count=("region", lambda s: s.replace("", pd.NA).dropna().nunique()))
        for eid, r in g.iterrows():
            if int(r.address_count) >= 5 or int(r.region_count) >= 3:
                rows.append(_signal(eid, "ADDRESS_HISTORY_BREADTH", "CURRENT", "LOW", "HIGH", f"Historial con {int(r.address_count)} direcciones y {int(r.region_count)} regiones distintas publicadas.", ["Revisar secuencia y vigencia de domicilios.", "Contextualizar con sucursales y naturaleza de la actividad."]))
    if not names.empty and not company_year.empty:
        current = names.dropna(subset=["entity_id"]).drop_duplicates("entity_id", keep="last")[["entity_id", "current_status"]]
        hist_term = company_year.assign(has_term=company_year["termination_date"].fillna("").ne("")).groupby("entity_id", dropna=True)["has_term"].max().reset_index()
        merged = current.merge(hist_term, on="entity_id", how="inner")
        for r in merged.itertuples(index=False):
            if r.current_status == "ACTIVE_AS_PUBLISHED" and bool(r.has_term):
                rows.append(_signal(r.entity_id, "REACTIVATION_PATTERN", "CURRENT", "LOW", "HIGH", "Existe término de giro en un registro histórico y la nómina vigente actual aparece sin término de giro.", ["Reconstruir la cronología de término/reinicio con datos SII.", "Tratarlo como evento de ciclo de vida, no como señal de ilicitud."]))
    return pd.DataFrame(rows)
