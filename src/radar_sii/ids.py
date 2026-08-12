from __future__ import annotations

import hashlib
import re
import unicodedata


def clean_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null", "<na>"} else text


def normalize_name(value: object) -> str:
    text = clean_text(value).upper()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip()


def normalize_rut(value: object, dv: object | None = None) -> str | None:
    raw = re.sub(r"[^0-9Kk]", "", clean_text(value))
    dv_raw = re.sub(r"[^0-9Kk]", "", clean_text(dv)) if dv is not None else ""
    if dv_raw and raw and len(raw) <= 8:
        raw = raw + dv_raw[-1]
    if len(raw) < 2:
        return None
    body, check = raw[:-1], raw[-1].upper()
    if not body.isdigit() or not rut_is_valid(body + check):
        return None
    return f"{int(body)}-{check}"


def rut_is_valid(compact: str) -> bool:
    compact = re.sub(r"[^0-9Kk]", "", clean_text(compact)).upper()
    if len(compact) < 2 or not compact[:-1].isdigit():
        return False
    body = compact[:-1]
    total = 0
    multiplier = 2
    for digit in reversed(body):
        total += int(digit) * multiplier
        multiplier = 2 if multiplier == 7 else multiplier + 1
    remainder = 11 - (total % 11)
    expected = "0" if remainder == 11 else "K" if remainder == 10 else str(remainder)
    return compact[-1] == expected


def entity_id(rut: str | None) -> str | None:
    return f"ENT-RUT-{rut}" if rut else None


def deterministic_id(prefix: str, *parts: object) -> str:
    payload = "|".join(clean_text(p) for p in parts)
    return f"{prefix}-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:24].upper()}"
