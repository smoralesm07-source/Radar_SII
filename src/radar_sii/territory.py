"""Resolución territorial contra el índice canónico del Context Hub.

Copia verbatim de `Context-Hub/interop/territory_adapter_reference.py`, con
`INDEX_PATH` ajustado al layout `src/` de este repositorio.
No editar aquí: cualquier cambio de criterio se hace en el hub y se re-vendoriza
junto con `config/territory_resolution_index_v1.json`.
"""


from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

# Ajustar a la ubicación del índice vendorizado dentro del radar.
INDEX_PATH = Path(__file__).resolve().parents[2] / "config" / "territory_resolution_index_v1.json"

_PREFIXES = (
    "REGION DE LA", "REGION DEL", "REGION DE", "REGION",
    "PROVINCIA DE LA", "PROVINCIA DEL", "PROVINCIA DE", "PROVINCIA",
    "COMUNA DE LA", "COMUNA DEL", "COMUNA DE", "COMUNA",
    "DE LA", "DEL", "DE",
)


def spaced_form(value: object) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(c for c in text if unicodedata.category(c) != "Mn").upper()
    return re.sub(r"[^A-Z0-9]+", " ", text).strip()


def strip_prefix(spaced: str) -> str:
    for prefix in _PREFIXES:
        if spaced == prefix:
            return ""
        if spaced.startswith(prefix + " "):
            return spaced[len(prefix) + 1:].strip()
    return spaced


def match_key(value: object) -> str:
    """Receta de clave del ecosistema. Debe coincidir bit a bit con el hub."""
    return strip_prefix(spaced_form(value)).replace(" ", "")


@lru_cache(maxsize=1)
def _index() -> dict:
    if not INDEX_PATH.exists():
        return {"index": {}, "max_key_len": 45, "compound_region": {}}
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


def _decompose_region(spaced: str) -> list[str]:
    """Separa numeral romano y nombre en una glosa regional compuesta."""
    cfg = _index().get("compound_region") or {}
    romans = set(cfg.get("romans") or ())
    words = set(cfg.get("region_words") or ())
    tokens = spaced.split()
    if not tokens:
        return []
    keys = [t for t in tokens if t in romans]
    rest = [t for t in tokens if t not in romans and t not in words]
    if rest:
        remainder = strip_prefix(" ".join(rest)).replace(" ", "")
        if remainder:
            keys.append(remainder)
    return keys


def resolve(text: object, level: str) -> tuple[str | None, str]:
    """Devuelve `(territory_id, mapping_status)`. `level` es REGION, PROVINCE o COMMUNE."""
    raw = str(text or "").strip()
    if not raw:
        return None, "UNKNOWN"

    data = _index()
    digits = re.fullmatch(r"(?:CL-(?:REG|PROV|COM)-)?(\d{2}|\d{3}|\d{5})", raw.upper())
    if digits:
        code = digits.group(1)
        prefix = {2: "REG", 3: "PROV", 5: "COM"}[len(code)]
        return f"CL-{prefix}-{code}", "CODE_EXACT"

    key = match_key(raw)
    if not key:
        return None, "UNKNOWN"
    if len(key) > data.get("max_key_len", 45):
        return None, "NOT_A_PLACE_NAME"

    found = data.get("index", {}).get(level, {}).get(key)
    if found:
        return found, "VALIDATED_EXACT"

    if level == "REGION":
        candidates = _decompose_region(spaced_form(raw))
        if len(candidates) >= 2:
            index = data.get("index", {}).get("REGION", {})
            hits = {index[c] for c in candidates if c in index}
            if len(hits) == 1:
                return next(iter(hits)), "VALIDATED_COMPOUND"
            if len(hits) > 1:
                return None, "CONFLICTING_SIGNALS"

    return None, "UNRESOLVED_NAME_ONLY"
