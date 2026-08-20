from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from .ids import deterministic_id, entity_id, normalize_rut

SOURCE_SYSTEM = "SII_CVC_VDC"
SOURCE_URL = "https://zeus.sii.cl/cvc/vdc/index.html"
OBSERVATION_KIND = "SPECIFIC_DOCUMENT_VERIFICATION"

# Códigos documentados por la Consulta Masiva Situación de Proveedores del SII.
DOCUMENT_TYPES = {
    "30": "FACTURA",
    "32": "FACTURA DE VENTAS Y SERVICIOS NO AFECTOS O EXENTOS IVA",
    "33": "FACTURA ELECTRONICA",
    "34": "FACTURA ELECTRONICA DE VENTAS Y SERVICIOS NO AFECTOS O EXENTOS IVA",
    "40": "LIQUIDACION FACTURA",
    "45": "FACTURA DE COMPRA",
    "46": "FACTURA DE COMPRA ELECTRONICA",
    "55": "NOTA DE DEBITO",
    "56": "NOTA DE DEBITO ELECTRONICA",
    "60": "NOTA DE CREDITO",
    "61": "NOTA DE CREDITO ELECTRONICA",
    "108": "SOLICITUD DE REGISTRO FACTURAS",
    "901": "FACTURA VENTA TERRITORIO PREFERENCIAL",
}

AUTHORIZED_RE = re.compile(r"AUTORIZAD[OA]\s+(?:EL\s+)?(\d{2})[-/]?(\d{2})[-/]?(\d{4})", re.I)
NOT_AUTHORIZED_RE = re.compile(r"NO\s+(?:SE\s+ENCUENTRA\s+)?AUTORIZAD[OA]", re.I)


@dataclass(frozen=True)
class DocumentAuthorizationObservation:
    authorization_record_id: str
    entity_id: str
    rut: str
    document_type_code: str
    document_type_name: str
    document_number: str
    document_date: str | None
    authorization_date: str | None
    authorization_status: str
    observation_kind: str
    source_system: str
    source_url: str
    source_response_sha256: str
    source_snapshot_id: str | None
    evidence_id: str
    observed_at: str


def _clean(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null", "<na>"} else text


def _iso_date(value: object) -> str | None:
    text = _clean(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def parse_sii_authorization_response(text: object) -> tuple[str, str | None]:
    """Return (status, authorization_date) from a normalized SII result string.

    The public SII service verifies a *specific* document. The parser therefore
    intentionally does not infer that the returned date is the taxpayer's latest
    timbraje; that broader statement requires complete coverage that the public
    query does not guarantee.
    """
    raw = _clean(text)
    if not raw:
        return "UNKNOWN", None
    match = AUTHORIZED_RE.search(raw)
    if match:
        day, month, year = match.groups()
        return "AUTHORIZED", date(int(year), int(month), int(day)).isoformat()
    if NOT_AUTHORIZED_RE.search(raw):
        return "NOT_AUTHORIZED", None
    return "UNKNOWN", None


def build_observation(
    *,
    rut: object,
    document_type_code: object,
    document_number: object,
    source_response: object,
    document_date: object = None,
    observed_at: object = None,
    source_snapshot_id: object = None,
) -> DocumentAuthorizationObservation:
    normalized_rut = normalize_rut(rut)
    if not normalized_rut:
        raise ValueError(f"RUT inválido: {rut!r}")
    code = _clean(document_type_code)
    number = _clean(document_number)
    if not number:
        raise ValueError("document_number es obligatorio")
    response = _clean(source_response)
    status, authorization_date = parse_sii_authorization_response(response)
    observed = _clean(observed_at) or datetime.now(timezone.utc).isoformat()
    doc_date = _iso_date(document_date)
    ent_id = entity_id(normalized_rut)
    if not ent_id:
        raise ValueError("No fue posible construir entity_id")
    response_sha = hashlib.sha256(response.encode("utf-8")).hexdigest()
    record_id = deterministic_id("SII-DOC-AUTH", normalized_rut, code, number, doc_date or "")
    evidence_id = deterministic_id("EVID", SOURCE_SYSTEM, normalized_rut, code, number, response_sha)
    return DocumentAuthorizationObservation(
        authorization_record_id=record_id,
        entity_id=ent_id,
        rut=normalized_rut,
        document_type_code=code,
        document_type_name=DOCUMENT_TYPES.get(code, "DOCUMENTO TRIBUTARIO"),
        document_number=number,
        document_date=doc_date,
        authorization_date=authorization_date,
        authorization_status=status,
        observation_kind=OBSERVATION_KIND,
        source_system=SOURCE_SYSTEM,
        source_url=SOURCE_URL,
        source_response_sha256=response_sha,
        source_snapshot_id=_clean(source_snapshot_id) or None,
        evidence_id=evidence_id,
        observed_at=observed,
    )


def normalize_frame(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    aliases = {
        "rut": ["rut", "RUT"],
        "document_type_code": ["document_type_code", "tipo_documento_codigo", "codigo_documento"],
        "document_number": ["document_number", "numero_documento", "folio"],
        "document_date": ["document_date", "fecha_documento"],
        "source_response": ["source_response", "respuesta_sii", "response"],
        "observed_at": ["observed_at", "fecha_consulta"],
        "source_snapshot_id": ["source_snapshot_id", "snapshot_id"],
    }

    def value(row: pd.Series, field: str) -> object:
        for name in aliases[field]:
            if name in row.index and _clean(row[name]):
                return row[name]
        return None

    for _, row in df.iterrows():
        try:
            obs = build_observation(
                rut=value(row, "rut"),
                document_type_code=value(row, "document_type_code"),
                document_number=value(row, "document_number"),
                document_date=value(row, "document_date"),
                source_response=value(row, "source_response"),
                observed_at=value(row, "observed_at"),
                source_snapshot_id=value(row, "source_snapshot_id"),
            )
        except ValueError:
            continue
        rows.append(asdict(obs))
    return pd.DataFrame(rows)


def latest_observed(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    work = df[df["authorization_status"].eq("AUTHORIZED")].copy()
    if work.empty:
        return work
    work["_auth"] = pd.to_datetime(work["authorization_date"], errors="coerce")
    work["_observed"] = pd.to_datetime(work["observed_at"], errors="coerce", utc=True)
    work = work.sort_values(["entity_id", "_auth", "_observed"], ascending=[True, False, False])
    return work.drop_duplicates("entity_id", keep="first").drop(columns=["_auth", "_observed"])


def write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.register("docauth", df)
    target = str(path).replace("'", "''")
    con.execute(f"COPY docauth TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)")


def _read_input(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".jsonl", ".ndjson"}:
        return pd.read_json(path, lines=True)
    if suffix == ".json":
        return pd.read_json(path)
    return pd.read_csv(path, sep=None, engine="python", dtype=str)


def main() -> None:
    parser = argparse.ArgumentParser(description="Normaliza evidencia de autorizaciones documentales SII")
    parser.add_argument("--input", required=True, help="CSV/JSON/JSONL con verificaciones documentales ya observadas")
    parser.add_argument("--out", default=".radar_sii/silver/sii_document_authorizations.parquet")
    parser.add_argument("--latest-out", default=".radar_sii/silver/sii_latest_document_authorization_observed.parquet")
    args = parser.parse_args()

    source = Path(args.input)
    df = normalize_frame(_read_input(source))
    latest = latest_observed(df)
    write_parquet(df, Path(args.out))
    write_parquet(latest, Path(args.latest_out))
    print(json.dumps({
        "source": str(source),
        "rows": int(len(df)),
        "authorized": int((df.get("authorization_status", pd.Series(dtype=str)) == "AUTHORIZED").sum()),
        "entities_with_authorized_observation": int(latest["entity_id"].nunique()) if not latest.empty else 0,
        "semantic": "LATEST_OBSERVED_AUTHORIZATION_NOT_ABSOLUTE_LAST_TIMBRAJE",
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
