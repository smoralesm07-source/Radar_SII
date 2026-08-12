# Schema Design — Radar SII v0.1.1

## Regla de arquitectura

`SOURCE_SNAPSHOT -> SOURCE_FACT -> CANONICAL_ENTITY -> DERIVED_FEATURE -> RISK_SIGNAL -> EVIDENCE`

Se replica el contrato conceptual de Radar CGR y Radar Presupuesto Abierto: hechos fuente separados de derivaciones, IDs estables, temporalidad explícita, trazabilidad y regeneración de analítica desde snapshots.

## SOURCE_SNAPSHOT

Campos mínimos:

`source_id, url, official_page, sha256, bytes, downloaded_at, etag, last_modified, published_update, coverage, normalization_version, selected_members`

Los datos masivos no se versionan en Git; metadata, reglas y salidas compactas sí.

## LEGAL_ENTITIES

Clave neutral al rol:

`entity_id = ENT-RUT-{RUT_VALIDADO}`

Campos actuales: RUT, razón social, nombre normalizado, código de subtipo, fecha vigente de inicio, fecha vigente de término de giro y estado derivado exclusivamente del snapshot publicado.

## COMPANY_YEAR

Grano: `entity_id + commercial_year`.

Campos canónicos principales:

- `commercial_year`
- `sales_band` / `sales_band_code` (SII 1-13)
- `workers`
- `region`, `province`, `commune`
- `economic_sector`, `economic_subsector`, `main_activity`
- `activity_start_date`
- `first_activity_registration_date`
- `termination_date`, `termination_type`
- `taxpayer_type`, `taxpayer_subtype`
- `positive_equity_band`, `negative_equity_band`
- `presumptive_income_regime`, `other_tax_regimes`

Los campos originales se preservan con prefijo `src_`.

## ENTITY_ACTIVITIES

Grano: actividad publicada por persona jurídica.

`entity_id, activity_code, activity_name, activity_registration_date, vat_affected, activity_category, activity_status, activity_record_id`

## ENTITY_ADDRESSES

Grano: domicilio/sucursal publicada.

`entity_id, address_status, address_date, address_type, street, street_number, block, apartment, village, city, commune, region, address_record_id`

Domicilios y sucursales se modelan en el mismo hecho de dirección, conservando la evidencia fuente.

## OWNERSHIP_EDGES

Grano: relación de composición publicada por SII.

`entity_id, society_type, society_subtype, partner_rut, partner_entity_id, natural_person_group_source, partner_id_type, partner_group_id, ownership_percent, relationship_type, ownership_record_id`

Valores de `partner_id_type`:

- `RUT`: socio persona jurídica con RUT validado.
- `NATURAL_PERSONS_AGGREGATE`: SII publica un agregado de personas naturales.
- `MISSING`: fuente sin identidad reutilizable.

**Regla AML de identidad:** `NATURAL_PERSONS_AGGREGATE` jamás se convierte en una persona, RUT ni beneficiario final inferido.

## DERIVED_FEATURES

Variables longitudinales regenerables:

- rango SII de ventas y variación interanual sólo cuando ambos años tienen información;
- dotación previa y ratio de dotación;
- edad aproximada desde inicio publicado;
- cambio de región;
- cambio de actividad principal;
- amplitud de actividades/domicilios;
- número de relaciones societarias salientes y sociedades en que una PJ aparece como socio.

## RISK_SIGNALS

Objeto central:

`signal_id, entity_id, signal_type, period, severity, severity_score, confidence, why_flagged, recommended_checks, source_record_id, generated_at`

Las señales son priorización y nunca sustituyen el hecho SII.

## ENTITY_SEARCH

Vista consolidada por `entity_id` que une:

1. estado/nombre actual;
2. último año empresarial publicado;
3. actividades actuales;
4. historia territorial;
5. resumen de relaciones societarias;
6. señales regeneradas.

Sirve como ficha rápida, mientras que `history`, `activities`, `addresses` y `ownership` conservan el detalle granular.

## Interoperabilidad futura

Cruces entre Radar SII, Radar CGR y Radar Presupuesto Abierto:

1. RUT validado / `entity_id` como clave primaria común.
2. nombre normalizado como apoyo, no sustituto del RUT.
3. período y territorio como contexto temporal/geográfico.
4. `ownership_edges` sólo como evidencia societaria publicada.
5. `evidence_links` con fuente, fundamento y confianza.

El integrador futuro deberá mantener separado: **hecho fuente → señal del radar → inferencia multicapa**.
