#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path('docs/data/timbraje_health.json')
PUBLIC_URL = 'https://www2.sii.cl/stc/noauthz'


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def public_probe() -> tuple[bool, str | None]:
    req = urllib.request.Request(PUBLIC_URL, headers={'User-Agent': 'Radar-SII/0.2 timbraje-health'})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return 200 <= getattr(r, 'status', 200) < 400, None
    except Exception as exc:
        return False, f'{type(exc).__name__}: {exc}'


def main() -> None:
    reachable, error = public_probe()
    token_present = bool(os.environ.get('SII_API_TOKEN', '').strip())
    endpoint_present = bool(os.environ.get('SII_QUERY_TIM_FACT_URL', '').strip())
    # QueryTimFact is an authenticated SII webservice. A public-site probe only
    # proves source availability; it must never be treated as a captured timbraje.
    if not reachable:
        status = 'SOURCE_UNAVAILABLE'
        reason = 'La consulta pública SII no respondió; no existe una captura verificable.'
    elif not (token_present and endpoint_present):
        status = 'AUTH_REQUIRED'
        reason = 'El servicio automatizado oficial de fecha último timbraje requiere endpoint autorizado y token SII.'
    else:
        status = 'AUTH_CONFIGURED_NO_MATERIALIZATION'
        reason = 'Credenciales detectadas, pero todavía no existe una observación materializada validada por el colector.'
    payload = {
        'schema': 'RADAR_SII_TIMBRAJE_HEALTH_V1',
        'checked_at': now_iso(),
        'status': status,
        'reason': reason,
        'public_query_url': PUBLIC_URL,
        'public_query_reachable': reachable,
        'public_probe_error': error,
        'official_service': 'QueryTimFact',
        'token_configured': token_present,
        'endpoint_configured': endpoint_present,
        'materialized_observations': 0,
        'latest_record_at': None,
        'semantic': 'No confundir disponibilidad de la consulta pública con fecha último timbraje capturada.'
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == '__main__':
    main()
