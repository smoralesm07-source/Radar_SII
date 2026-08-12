# Motor de búsqueda — Radar SII

## Diseño

El motor reconstruye las fuentes oficiales en el runner, normaliza por bloques a Parquet y consulta con DuckDB. Esto evita mantener una base masiva en GitHub y permite una búsqueda reproducible sin servidor externo.

## Ámbitos

### `entities`
Ficha consolidada por RUT con razón social, vigencia, última observación anual disponible, actividad, territorio y señales.

### `history`
Serie anual por empresa con tramo de ventas, trabajadores, región, rubro, actividad, capital propio tributario y variables interanuales.

### `activities`
Actividades económicas publicadas como vigentes.

### `addresses`
Historial de direcciones publicadas para casa matriz/sucursales.

### `signals`
Señales analíticas con su explicación y controles recomendados.

## Parámetros

Texto libre busca sobre los campos relevantes del ámbito. `filters_json` admite, cuando la columna existe:

- `rut`, `entity_id`
- `year`, `year_from`, `year_to`
- `region`, `commune`
- `sales_band`, `min_sales_rank`, `max_sales_rank`
- `min_workers`, `max_workers`
- `economic_sector`, `economic_subsector`
- `activity_code`, `main_activity`
- `taxpayer_type`, `taxpayer_subtype`
- `current_status`
- `start_date_from`, `start_date_to`
- `termination_date_from`, `termination_date_to`
- `signal_type`, `severity`
- `min_signal_count`, `min_address_count`, `min_activity_count`

Ejemplos:

```json
{"rut":"76086428-5"}
```

```json
{"year_from":2022,"year_to":2024,"min_sales_rank":9,"max_workers":2}
```

```json
{"economic_sector":"CONSTRUCCION","region":"XIII REGION METROPOLITANA"}
```

La coincidencia de búsqueda es un hecho recuperado; no implica señal AML. Una señal es priorización y requiere revisión humana/contextual.
