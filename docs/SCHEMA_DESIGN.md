# Schema Design — Radar SII v0.1

## Regla de arquitectura

`SOURCE_SNAPSHOT -> SOURCE_FACT -> CANONICAL_ENTITY -> DERIVED_FEATURE -> RISK_SIGNAL -> EVIDENCE`

Se replica el contrato conceptual de Radar CGR y Radar Presupuesto Abierto: hechos de fuente separados de derivaciones, IDs estables, trazabilidad y posibilidad de regenerar analítica desde los snapshots.

## SOURCE_SNAPSHOT

Campos mínimos: `source_id`, `url`, `sha256`, `bytes`, `downloaded_at`, `etag`, `last_modified`, cobertura publicada y versión de normalización.

Los datos masivos no se versionan en Git; la metadata sí puede publicarse en `docs/data/`.

## LEGAL_ENTITIES

Clave: `entity_id = ENT-RUT-{RUT_VALIDADO}`.

Campos: RUT, razón social, nombre normalizado, fecha de inicio, fecha de término de giro publicada, estado actual derivado de la nómina y snapshot.

La clave `ENT-RUT-*` es deliberadamente neutral al rol: una misma persona jurídica puede ser proveedor, receptor de gasto, auditado, empleador u otra condición según cada radar.

## COMPANY_YEAR

Grano: `entity_id + commercial_year` según registro fuente.

Campos canónicos:

- `commercial_year`
- `sales_band`
- `workers`
- `region`
- `economic_sector`
- `economic_subsector`
- `main_activity`
- `activity_start_date`
- `termination_date`
- `termination_type`
- `taxpayer_type`
- `taxpayer_subtype`
- `positive_equity_band`
- `negative_equity_band`

Los campos fuente originales se preservan con prefijo `src_` para auditoría y evolución del esquema.

## ENTITY_ACTIVITIES

Grano: actividad publicada por persona jurídica. Conserva código, glosa, categoría/estado cuando estén presentes y `activity_record_id` determinístico.

## ENTITY_ADDRESSES

Grano: dirección histórica publicada. Conserva tipo, calle, número, bloque/departamento, localidad, comuna, región y estado/vigencia cuando estén presentes.

## DERIVED_FEATURES y RISK_SIGNALS

Las variables derivadas se calculan sobre Parquet con DuckDB. Las señales se regeneran y nunca sobrescriben los hechos fuente. Cada señal mantiene `entity_id`, período, severidad, confianza, explicación y controles recomendados.

## Interoperabilidad futura

Cruces futuros se realizan por:

1. RUT formalmente validado / `entity_id`.
2. nombre normalizado como apoyo, nunca como identidad suficiente cuando exista RUT.
3. período y territorio.
4. `evidence_links` con fuente, fundamento y confianza.

No se copiarán señales de un radar como si fueran hechos de otro; el sistema mayor deberá distinguir evidencia CGR, gasto público, SII y cualquier inferencia de correlación.
