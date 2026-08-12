# Motor de búsqueda — Radar SII v0.1.1

## Objetivo

Recuperar hechos SII por entidad con suficiente trazabilidad para pasar desde una consulta exploratoria a una revisión AML/OSINT reproducible. Coincidencia de búsqueda no equivale a señal; señal no equivale a irregularidad.

## Ámbitos

- `entities`: ficha consolidada actual + último año + contadores societarios y señales.
- `history`: serie anual 2020-2024 por entidad.
- `activities`: actividades económicas vigentes/publicadas.
- `addresses`: domicilios y sucursales históricas.
- `ownership`: composición societaria publicada por SII.
- `signals`: señales determinísticas regeneradas.

## Filtros principales

### Identidad

- `rut`
- `entity_id`
- `partner_rut`
- `partner_entity_id`
- `partner_id_type`

### Tiempo y estado

- `year`, `year_from`, `year_to`
- `current_status`
- `start_date_from`, `start_date_to`
- `termination_date_from`, `termination_date_to`
- `activity_date_from`, `activity_date_to`
- `address_date_from`, `address_date_to`

### Actividad y territorio

- `region`, `commune`
- `economic_sector`, `economic_subsector`, `main_activity`
- `activity_code`
- `taxpayer_type`, `taxpayer_subtype`, `taxpayer_subtype_code`

### Escala empresarial

- `sales_band`, `sales_band_code`
- `min_sales_rank`, `max_sales_rank`
- `min_workers`, `max_workers`

### Sociedad

- `society_type`, `society_subtype`
- `min_ownership_percent`, `max_ownership_percent`
- `min_ownership_edges`
- `min_societies_as_partner`

### Señales

- `signal_type`, `severity`
- `min_signal_count`
- `min_activity_count`, `min_address_count`

## Texto libre

La búsqueda textual recorre sólo columnas existentes en el ámbito solicitado: razón social, RUT/IDs, actividad, rubro, territorio, señales y atributos societarios. Los filtros estructurados se parametrizan; no se interpolan valores del usuario directamente en SQL.

## Trazabilidad de cada consulta

El artifact contiene:

- `result.csv`
- `result.json`
- `query_metadata.json`
- `snapshot_manifest.json`
- `source_catalog.json`
- `coverage.json`
- `quality.json`

`query_metadata.json` registra ámbito, texto, filtros, límite, filas, años empresariales observados y estado de cobertura histórica. `snapshot_manifest.json` identifica los ZIP oficiales exactos mediante SHA-256 y miembros internos procesados.

## Ejemplos

Ficha de entidad:

```json
{"rut":"76086428-5"}
```

Trayectoria 2020-2024:

```json
{"rut":"76086428-5","year_from":2020,"year_to":2024}
```

Empresas de una región con tramo alto y poca dotación:

```json
{"region":"METROPOLITANA","min_sales_rank":10,"max_workers":2}
```

Sociedades donde una persona jurídica aparece como socio:

```json
{"partner_rut":"76086428-5","min_ownership_percent":10}
```

Señal longitudinal:

```json
{"signal_type":"WORKFORCE_DROP_STABLE_SALES"}
```

## Principios AML

- El tramo de ventas SII es ordinal y tributario, no una venta monetaria exacta.
- `sales_band_code=1` significa sin información y no se usa como base de un salto.
- Una relación `OWNERSHIP_AS_PUBLISHED` no implica control efectivo ni beneficiario final.
- `NATURAL_PERSONS_AGGREGATE` nunca se individualiza.
- Un cambio registral es contexto; requiere contraste con historia, actividad y otras fuentes.
- La integración futura con CGR/Presupuesto Abierto debe preservar el origen de cada evidencia.
