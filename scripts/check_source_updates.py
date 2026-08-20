#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SOURCES = {
    'sii_company_year': 'https://www.sii.cl/estadisticas/nominas/PUB_EMPRESAS_PJ_2020_A_2024.zip',
    'sii_names_current': 'https://www.sii.cl/estadisticas/nominas/PUB_NOMBRES_PJ.zip',
    'sii_activities_current': 'https://www.sii.cl/estadisticas/nominas/PUB_NOM_ACTECOS.zip',
    'sii_addresses_history': 'https://www.sii.cl/estadisticas/nominas/PUB_NOM_DIRECCIONES.zip',
    'sii_ownership_current': 'https://www.sii.cl/sobre_el_sii/composicion_sociedades.zip',
}
STATE = Path('docs/data/sii_source_watch.json')


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def probe(url: str) -> dict:
    headers = {'User-Agent': 'Radar-SII/0.2 source-watch'}
    request = urllib.request.Request(url, method='HEAD', headers=headers)
    try:
        response = urllib.request.urlopen(request, timeout=60)
    except urllib.error.HTTPError as exc:
        if exc.code not in {400, 403, 405, 501}:
            raise
        request = urllib.request.Request(url, headers={**headers, 'Range': 'bytes=0-0'})
        response = urllib.request.urlopen(request, timeout=60)
    with response as r:
        content_range = r.headers.get('Content-Range') or ''
        total = content_range.rsplit('/', 1)[-1] if '/' in content_range else r.headers.get('Content-Length')
        return {
            'url': url,
            'etag': r.headers.get('ETag'),
            'last_modified': r.headers.get('Last-Modified'),
            'content_length': total,
            'http_status': getattr(r, 'status', 200),
        }


def fingerprint(row: dict) -> str:
    return '|'.join(str(row.get(k) or '') for k in ('etag', 'last_modified', 'content_length'))


def main() -> None:
    prior = json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {}
    old = prior.get('sources') if isinstance(prior, dict) else {}
    checked_at = now_iso()
    rows = {}
    changed = []
    errors = []
    for source_id, url in SOURCES.items():
        try:
            row = probe(url)
            row['fingerprint'] = fingerprint(row)
            previous = (old or {}).get(source_id) or {}
            row['changed_since_previous_check'] = bool(previous.get('fingerprint') and previous.get('fingerprint') != row['fingerprint'])
            if row['changed_since_previous_check']:
                changed.append(source_id)
            rows[source_id] = row
        except Exception as exc:
            errors.append({'source_id': source_id, 'error': f'{type(exc).__name__}: {exc}'})
            rows[source_id] = {'url': url, 'error': errors[-1]['error'], 'fingerprint': None, 'changed_since_previous_check': False}
    payload = {
        'schema': 'RADAR_SII_SOURCE_WATCH_V1',
        'checked_at': checked_at,
        'status': 'SUCCESS' if not errors else ('PARTIAL' if len(errors) < len(SOURCES) else 'FAILED'),
        'first_baseline': not bool(old),
        'changed_sources': changed,
        'source_changed': bool(changed),
        'errors': errors,
        'sources': rows,
    }
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(payload, ensure_ascii=False))
    if len(errors) == len(SOURCES):
        raise SystemExit('No fue posible verificar ninguna fuente SII oficial')


if __name__ == '__main__':
    main()
