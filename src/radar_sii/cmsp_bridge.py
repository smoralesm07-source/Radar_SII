from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

import pandas as pd

from .document_authorizations import normalize_frame, write_parquet
from .ids import normalize_rut

MAX_RECORDS = 10_000

DOCUMENT_NAME_TO_CODE = {
    "FACTURA": "30",
    "FACTURA ELECTRONICA": "33",
    "FACTURA EXENTA": "32",
    "FACTURA NO AFECTA": "32",
    "FACTURA ELECTRONICA EXENTA": "34",
    "FACTURA ELECTRONICA NO AFECTA": "34",
    "LIQUIDACION FACTURA": "40",
    "FACTURA DE COMPRA": "45",
    "FACTURA DE COMPRA ELECTRONICA": "46",
    "NOTA DE DEBITO": "55",
    "NOTA DE DEBITO ELECTRONICA": "56",
    "NOTA DE CREDITO": "60",
    "NOTA DE CREDITO ELECTRONICA": "61",
    "SOLICITUD DE REGISTRO FACTURAS": "108",
    "FACTURA VENTA TERRITORIO PREFERENCIAL": "901",
}
VALID_CODES = {"30", "32", "33", "34", "40", "45", "46", "55", "56", "60", "61", "108", "901"}


def _clean(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null", "<na>"} else text


def _norm_name(value: object) -> str:
    text = _clean(value).upper()
    text = re.sub(r"[^A-Z0-9ÁÉÍÓÚÜÑ ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def document_code(value: object) -> str | None:
    raw = _clean(value)
    if raw in VALID_CODES:
        return raw
    name = _norm_name(raw)
    if name in DOCUMENT_NAME_TO_CODE:
        return DOCUMENT_NAME_TO_CODE[name]
    # Conservative aliases only. Unknown descriptions are not guessed.
    if "FACTURA" in name and "ELECTRON" in name and ("EXENTA" in name or "NO AFECTA" in name):
        return "34"
    if name.startswith("FACTURA") and "ELECTRON" in name:
        return "33"
    if name.startswith("FACTURA") and ("EXENTA" in name or "NO AFECTA" in name):
        return "32"
    if name == "FACTURA":
        return "30"
    if "NOTA" in name and "CREDITO" in name and "ELECTRON" in name:
        return "61"
    if "NOTA" in name and "CREDITO" in name:
        return "60"
    if "NOTA" in name and "DEBITO" in name and "ELECTRON" in name:
        return "56"
    if "NOTA" in name and "DEBITO" in name:
        return "55"
    return None


def _date_yyyymmdd(value: object) -> str | None:
    text = _clean(value)
    if not text:
        return None
    dt = pd.to_datetime(text, errors="coerce", dayfirst=True)
    if pd.isna(dt):
        return None
    return dt.strftime("%Y%m%d")


def _pick(row: pd.Series, names: tuple[str, ...]) -> object:
    for name in names:
        if name in row.index and _clean(row[name]):
            return row[name]
    return None


def prepare_cmsp_records(df: pd.DataFrame, max_records: int = MAX_RECORDS) -> tuple[list[list[str]], dict]:
    records: list[list[str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    skipped = {"invalid_rut": 0, "unsupported_document_type": 0, "missing_document_number": 0, "missing_document_date": 0, "duplicate": 0}

    for _, row in df.iterrows():
        rut = normalize_rut(_pick(row, ("rut", "rut_beneficiario", "provider_rut", "rut_proveedor")))
        if not rut:
            skipped["invalid_rut"] += 1
            continue
        code = document_code(_pick(row, ("document_type_code", "tipo_documento", "document_type", "codigo_documento")))
        if not code:
            skipped["unsupported_document_type"] += 1
            continue
        number = _clean(_pick(row, ("numero_documento", "document_number", "folio")))
        if not number:
            skipped["missing_document_number"] += 1
            continue
        doc_date = _date_yyyymmdd(_pick(row, ("fecha_documento", "document_date")))
        if not doc_date:
            skipped["missing_document_date"] += 1
            continue
        body, dv = rut.split("-", 1)
        key = (body, code, number, doc_date)
        if key in seen:
            skipped["duplicate"] += 1
            continue
        seen.add(key)
        records.append([body, dv, code, number, doc_date])
        if len(records) >= max_records:
            break

    meta = {
        "input_rows": int(len(df)),
        "prepared_records": len(records),
        "limit": int(max_records),
        "skipped": skipped,
        "format": "RUT_BODY;DV;DOCUMENT_CODE;DOCUMENT_NUMBER;YYYYMMDD",
        "semantic": "SPECIFIC_DOCUMENT_VERIFICATION_CANDIDATES",
    }
    return records, meta


def write_cmsp_input(records: list[list[str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter=";", lineterminator="\n")
        writer.writerows(records)


def parse_cmsp_response(path: Path) -> pd.DataFrame:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as fh:
        reader = csv.reader(fh, delimiter=";")
        for values in reader:
            if len(values) < 6:
                continue
            body, dv, code, number, doc_date = (v.strip() for v in values[:5])
            response = ";".join(values[5:]).strip()
            if not (body and dv and code and number):
                continue
            rows.append({
                "rut": f"{body}-{dv}",
                "document_type_code": code,
                "document_number": number,
                "document_date": doc_date,
                "source_response": response,
            })
    return normalize_frame(pd.DataFrame(rows)) if rows else pd.DataFrame()


def _read_candidates(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        return pd.read_json(path, lines=True)
    if path.suffix.lower() == ".json":
        return pd.read_json(path)
    return pd.read_csv(path, sep=None, engine="python", dtype=str)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bridge gobernado hacia/desde Consulta Masiva Situación de Proveedores SII")
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare", help="Genera archivo CMSP desde documentos candidatos")
    prepare.add_argument("--input", required=True)
    prepare.add_argument("--out", default=".radar_sii/cmsp/document_candidates.txt")
    prepare.add_argument("--meta-out", default=".radar_sii/cmsp/document_candidates.json")
    prepare.add_argument("--max-records", type=int, default=MAX_RECORDS)

    parse = sub.add_parser("parse", help="Normaliza el archivo de respuesta descargado desde SII")
    parse.add_argument("--input", required=True)
    parse.add_argument("--out", default=".radar_sii/silver/sii_document_authorizations.parquet")

    args = parser.parse_args()
    if args.command == "prepare":
        source = _read_candidates(Path(args.input))
        records, meta = prepare_cmsp_records(source, max(1, min(int(args.max_records), MAX_RECORDS)))
        write_cmsp_input(records, Path(args.out))
        meta_path = Path(args.meta_out)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(meta, ensure_ascii=False))
        return

    normalized = parse_cmsp_response(Path(args.input))
    write_parquet(normalized, Path(args.out))
    print(json.dumps({
        "response_rows": int(len(normalized)),
        "authorized": int((normalized.get("authorization_status", pd.Series(dtype=str)) == "AUTHORIZED").sum()),
        "semantic": "LATEST_OBSERVED_AUTHORIZATION_NOT_ABSOLUTE_LAST_TIMBRAJE",
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
