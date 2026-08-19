from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd
import requests

CHILECOMPRA_API = (
    "https://api.mercadopublico.cl/servicios/v1/Publico/Empresas/BuscarComprador"
    "?ticket=F8537A18-6766-4DEF-9E59-426B4FEE2844"
)
CHILECOMPRA_PAGE = "https://datos-abiertos.chilecompra.cl/organismos-compradores"
DATOS_GOB_ORGS_API = "https://datos.gob.cl/api/3/action/organization_list?all_fields=true"
DATOS_GOB_ORGS_PAGE = "https://datos.gob.cl/organization/"
DIPRES_2026 = "https://www.dipres.gob.cl/597/w3-multipropertyvalues-15145-37782.html"
DIPRES_INSTITUTIONS = "https://www.dipres.gob.cl/597/w3-propertyname-557.html"


def norm(value: object) -> str:
    text = str(value or "").strip().upper()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\bI\.?\s+MUNICIPALIDAD\b", "MUNICIPALIDAD", text)
    text = re.sub(r"\bILUSTRE\s+MUNICIPALIDAD\b", "MUNICIPALIDAD", text)
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def public_id(name: str) -> str:
    token = hashlib.sha256(f"PUBLIC_ENTITY_CHILE|{norm(name)}".encode("utf-8")).hexdigest()[:20].upper()
    return f"PUB-CL-{token}"


class HeadingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.depth = 0
        self.parts: list[str] = []
        self.headings: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {"h2", "h3", "h4"}:
            self.depth += 1
            if self.depth == 1:
                self.parts = []

    def handle_data(self, data: str) -> None:
        if self.depth:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"h2", "h3", "h4"} and self.depth:
            self.depth -= 1
            if self.depth == 0:
                text = " ".join(x.strip() for x in self.parts if x.strip()).strip()
                if text:
                    self.headings.append(text)
                self.parts = []


def fetch_json(session: requests.Session, url: str) -> dict:
    r = session.get(url, timeout=90, headers={"User-Agent": "Radar-SII/0.2 public-entity-registry"})
    r.raise_for_status()
    return r.json()


def fetch_headings(session: requests.Session, url: str) -> list[str]:
    r = session.get(url, timeout=90, headers={"User-Agent": "Radar-SII/0.2 public-entity-registry"})
    r.raise_for_status()
    parser = HeadingParser()
    parser.feed(r.text)
    noise = {
        "LEY DE PRESUPUESTOS", "PROYECTO DE LEY", "EJECUCION", "GESTION",
        "DOCUMENTO EXCEL", "DOCUMENTO PDF", "PRESUPUESTOS",
    }
    return [h for h in parser.headings if norm(h) not in noise and 2 <= len(norm(h)) <= 160]


def classify(name: str) -> str:
    n = norm(name)
    if "MUNICIPALIDAD" in n:
        return "MUNICIPALITY"
    if n.startswith("GOBIERNO REGIONAL"):
        return "REGIONAL_GOVERNMENT"
    if "DELEGACION PRESIDENCIAL" in n or n.startswith("GOBERNACION PROVINCIAL"):
        return "PRESIDENTIAL_DELEGATION"
    if "HOSPITAL" in n or n.startswith("SERVICIO DE SALUD") or "CONSULTORIO" in n or "CENTRO DE SALUD" in n:
        return "PUBLIC_HEALTH"
    if n.startswith("MINISTERIO ") or n.startswith("SUBSECRETARIA ") or "SECRETARIA REGIONAL MINISTERIAL" in n:
        return "MINISTRY_OR_SUBSECRETARIAT"
    if n.startswith("SUPERINTENDENCIA ") or "COMISION PARA EL MERCADO FINANCIERO" in n:
        return "SUPERVISOR_OR_REGULATOR"
    if any(x in n for x in ("CARABINEROS", "POLICIA DE INVESTIGACIONES", "EJERCITO", "ARMADA", "FUERZA AEREA", "GENDARMERIA")):
        return "DEFENCE_OR_PUBLIC_SECURITY"
    if n.startswith("EMPRESA ") or n.startswith("BANCO DEL ESTADO") or "METRO S A" in n or "TELEVISION NACIONAL" in n:
        return "STATE_COMPANY_OR_PUBLIC_CORPORATION"
    if n.startswith("UNIVERSIDAD ") or "CENTRO DE FORMACION TECNICA ESTATAL" in n:
        return "STATE_HIGHER_EDUCATION"
    if n.startswith("SERVICIO ") or n.startswith("DIRECCION ") or n.startswith("INSTITUTO ") or n.startswith("AGENCIA "):
        return "PUBLIC_SERVICE_OR_AGENCY"
    return "OTHER_PUBLIC_ENTITY"


def build_sii_lookup(names_parquet: Path) -> dict[str, tuple[str, str, str]]:
    if not names_parquet.exists():
        return {}
    df = pd.read_parquet(names_parquet, columns=["rut", "entity_id", "legal_name", "legal_name_norm"])
    df = df.dropna(subset=["entity_id"]).copy()
    aliases: list[tuple[str, str, str, str]] = []
    for row in df.itertuples(index=False):
        legal = str(row.legal_name or "").strip()
        key = norm(legal)
        if key:
            aliases.append((key, str(row.rut or ""), str(row.entity_id or ""), legal))
        if key.startswith("FISCO DE CHILE "):
            alias = key.removeprefix("FISCO DE CHILE ").strip()
            if alias:
                aliases.append((alias, str(row.rut or ""), str(row.entity_id or ""), legal))
    adf = pd.DataFrame(aliases, columns=["key", "rut", "entity_id", "legal_name"])
    if adf.empty:
        return {}
    counts = adf.groupby("key")["entity_id"].nunique()
    unique_keys = set(counts[counts == 1].index)
    adf = adf[adf["key"].isin(unique_keys)].drop_duplicates("key")
    return {r.key: (r.rut, r.entity_id, r.legal_name) for r in adf.itertuples(index=False)}


def datos_gob_orgs(session: requests.Session) -> list[dict]:
    try:
        payload = fetch_json(session, DATOS_GOB_ORGS_API)
    except Exception:
        return []
    result = payload.get("result") if payload.get("success") is not False else []
    return result if isinstance(result, list) else []


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--names-parquet", default=".public_registry/silver/sii_names_current.parquet")
    p.add_argument("--output", default="config/public_entities_registry.csv")
    p.add_argument("--summary", default="docs/data/public_entities_summary.json")
    args = p.parse_args()

    session = requests.Session()
    buyers_payload = fetch_json(session, CHILECOMPRA_API)
    buyers = buyers_payload.get("listaEmpresas") or []
    open_data_orgs = datos_gob_orgs(session)

    dipres_headings = fetch_headings(session, DIPRES_2026)
    try:
        dipres_headings.extend(fetch_headings(session, DIPRES_INSTITUTIONS))
    except Exception:
        pass
    dipres_keys = {norm(x) for x in dipres_headings if norm(x)}

    # Canonicalización por nombre institucional normalizado. ChileCompra y Datos.gob son evidencias
    # complementarias; conservar ambas evita confundir 'organismo comprador' con 'servicio público estricto'.
    universe: dict[str, dict] = {}
    for item in buyers:
        code = str(item.get("CodigoEmpresa") or "").strip()
        name = str(item.get("NombreEmpresa") or "").strip()
        key = norm(name)
        if not code or not key:
            continue
        universe[key] = {
            "official_name": name,
            "chilecompra_code": code,
            "chilecompra_reference_match": True,
            "datos_gob_code": "",
            "datos_gob_reference_match": False,
        }

    for item in open_data_orgs:
        name = str(item.get("title") or item.get("display_name") or item.get("name") or "").strip()
        code = str(item.get("name") or item.get("id") or "").strip()
        key = norm(name)
        if not key:
            continue
        if key not in universe:
            universe[key] = {
                "official_name": name,
                "chilecompra_code": "",
                "chilecompra_reference_match": False,
                "datos_gob_code": code,
                "datos_gob_reference_match": True,
            }
        else:
            universe[key]["datos_gob_code"] = code
            universe[key]["datos_gob_reference_match"] = True

    sii_lookup = build_sii_lookup(Path(args.names_parquet))
    rows: list[dict] = []
    for key, item in universe.items():
        name = item["official_name"]
        rut = entity_id = sii_legal_name = ""
        match_method = "NO_RUT_MATCH"
        match_confidence = "UNMATCHED"
        if key in sii_lookup:
            rut, entity_id, sii_legal_name = sii_lookup[key]
            match_method = "EXACT_NORMALIZED_NAME_UNIQUE"
            match_confidence = "HIGH"
        dipres_match = key in dipres_keys
        sources = []
        source_codes = []
        if item["chilecompra_reference_match"]:
            sources.append("CHILECOMPRA_MERCADO_PUBLICO")
            source_codes.append(f"CHILECOMPRA:{item['chilecompra_code']}")
        if item["datos_gob_reference_match"]:
            sources.append("DATOS_GOB_INSTITUTIONS")
            if item["datos_gob_code"]:
                source_codes.append(f"DATOS_GOB:{item['datos_gob_code']}")
        rows.append({
            "public_entity_id": public_id(name),
            "official_name": name,
            "official_name_norm": key,
            "source_system": " | ".join(sources),
            "source_code": " | ".join(source_codes),
            "is_public_entity": "true",
            "is_public_service_strict": "true" if dipres_match else "false",
            "public_entity_type": classify(name),
            "chilecompra_reference_match": "true" if item["chilecompra_reference_match"] else "false",
            "datos_gob_reference_match": "true" if item["datos_gob_reference_match"] else "false",
            "dipres_reference_match": "true" if dipres_match else "false",
            "rut": rut,
            "entity_id": entity_id,
            "sii_legal_name": sii_legal_name,
            "sii_match_method": match_method,
            "sii_match_confidence": match_confidence,
            "source_url": CHILECOMPRA_PAGE if item["chilecompra_reference_match"] else DATOS_GOB_ORGS_PAGE,
            "source_api_url": CHILECOMPRA_API if item["chilecompra_reference_match"] else DATOS_GOB_ORGS_API,
            "strict_reference_url": DIPRES_2026,
        })

    out = pd.DataFrame(rows).drop_duplicates("public_entity_id")
    out = out.sort_values(["public_entity_type", "official_name"])
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(target, sep=";", index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)

    matched = out[out["entity_id"].astype(str) != ""]
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "public_entities_total": int(len(out)),
        "public_entities_chilecompra": int((out["chilecompra_reference_match"] == "true").sum()),
        "public_entities_datos_gob": int((out["datos_gob_reference_match"] == "true").sum()),
        "strict_public_services_dipres_matched_by_name": int((out["is_public_service_strict"] == "true").sum()),
        "sii_rut_exact_matches": int(len(matched)),
        "sii_match_rate": round(len(matched) / len(out), 6) if len(out) else 0,
        "types": {str(k): int(v) for k, v in out["public_entity_type"].value_counts().items()},
        "sources": {
            "chilecompra": CHILECOMPRA_API,
            "chilecompra_description": CHILECOMPRA_PAGE,
            "datos_gob_institutions": DATOS_GOB_ORGS_API,
            "datos_gob_directory": DATOS_GOB_ORGS_PAGE,
            "dipres_2026": DIPRES_2026,
            "dipres_institutions": DIPRES_INSTITUTIONS,
        },
        "identity_rule": "RUT/entity_id solo se asigna por coincidencia normalizada exacta y unívoca contra la nómina SII; no se usa fuzzy matching automático.",
        "interpretation": {
            "is_public_entity": "Entidad observada en al menos una fuente oficial institucional: ChileCompra o directorio Datos.gob.",
            "is_public_service_strict": "Nombre del organismo también observado en referencia institucional/presupuestaria DIPRES.",
            "chilecompra_reference_match": "Organismo comprador publicado por Mercado Público.",
            "datos_gob_reference_match": "Institución publicada en el directorio oficial de Datos.gob.",
        },
    }
    sp = Path(args.summary)
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
