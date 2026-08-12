# Radar SII

Radar OSINT para transformar información pública del **Servicio de Impuestos Internos de Chile (SII)** en datos empresariales históricos, trazables y reutilizables para inteligencia de riesgo con enfoque AML/LA-FT.

> Una señal estadística, cambio registral o inconsistencia aparente no acredita por sí sola lavado de activos, evasión, delito ni irregularidad. El sistema prioriza revisión y conserva la evidencia de origen.

## v0.1 — Registro empresarial e inteligencia temporal

La primera versión utiliza fuentes públicas masivas del SII y cubre, según disponibilidad oficial, desde **2020 hasta el último período publicado**. El núcleo histórico granular disponible actualmente corresponde a los años comerciales **2020-2024**, complementado con nóminas registrales vigentes publicadas por SII en **agosto de 2026**.

### Variables principales

- RUT validado y `entity_id` canónico.
- Razón social normalizada.
- Fecha de inicio de actividades.
- Fecha y tipo de término de giro cuando la fuente lo publica.
- Estado registral derivado exclusivamente de la nómina publicada.
- Tramo de ventas anual.
- Número de trabajadores informado por año.
- Región asociada a la empresa en la nómina anual.
- Rubro, subrubro y actividad económica principal.
- Tipo y subtipo de contribuyente.
- Tramos de capital propio tributario positivo y negativo.
- Actividades económicas vigentes.
- Direcciones históricas, comuna y región cuando están disponibles.

## Arquitectura común de radares

```text
SOURCE_SNAPSHOT
      |
      v
SOURCE_FACT
      |
      v
NORMALIZED_FACT
      |
      +---- Parquet + DuckDB structured search
      |
      v
DERIVED_FEATURE
      |
      v
RISK_SIGNAL
      |
      v
EVIDENCE / LINEAGE
```

El modelo replica los principios de Radar CGR y Radar Presupuesto Abierto: separación estricta entre evidencia fuente, normalización, variables derivadas e inferencias; snapshots con SHA-256; identificadores estables; almacenamiento analítico en Parquet; y resultados pesados fuera de Git.

## Identidad interoperable

Para toda persona jurídica con RUT formalmente válido:

```text
entity_id = ENT-RUT-{RUT_NORMALIZADO}
```

Este identificador está diseñado para ser reutilizado por una futura capa común de resolución de entidades entre Radar SII, Radar CGR y Radar Presupuesto Abierto. No se infiere identidad cuando el RUT no supera la validación de dígito verificador.

## Fuentes SII v0.1

1. Nómina de empresas personas jurídicas, años comerciales 2020-2024.
2. Nómina actual de razones sociales, inicio de actividades y término de giro.
3. Nómina de actividades económicas vigentes.
4. Nómina de direcciones históricas.

Las URL oficiales y sus metadatos se mantienen en `config/sources.yaml`. Los archivos masivos descargados no se versionan en Git.

## Modelo principal

- `source_snapshots`
- `legal_entities`
- `company_year`
- `entity_activities`
- `entity_addresses`
- `derived_features`
- `risk_signals`
- `evidence_links`

La tabla `company_year` es longitudinal y permite observar la trayectoria 2020-2024 por RUT. Las nóminas actuales enriquecen el estado registral a la fecha de publicación de la fuente.

## Señales iniciales

Las reglas son determinísticas, explicables y recalculables:

- `SALES_BAND_JUMP`: salto relevante de tramo de ventas interanual.
- `HIGH_SALES_LOW_WORKFORCE`: ventas altas con dotación muy reducida o nula.
- `RECENT_START_HIGH_SALES`: empresa joven que alcanza rápidamente tramos altos de ventas.
- `HIGH_SALES_NEGATIVE_EQUITY`: coexistencia de tramo alto de ventas y capital propio tributario negativo publicado.
- `REGION_CHANGE`: cambio de región entre períodos consecutivos.
- `ACTIVITY_BREADTH`: amplitud elevada de actividades económicas vigentes.
- `ADDRESS_HISTORY_BREADTH`: cantidad elevada de domicilios históricos publicados.
- `REACTIVATION_PATTERN`: patrón registral que requiere revisión temporal adicional.

Cada señal conserva `why_flagged`, severidad, confianza, período, valores observados y controles recomendados. No equivale a una calificación de riesgo legal ni tributario efectuada por el SII.

## Motor de búsqueda

El workflow **Search Radar SII** permite consultar cinco ámbitos:

- `entities`: ficha consolidada por RUT.
- `history`: serie empresa-año.
- `activities`: actividades económicas vigentes.
- `addresses`: domicilios históricos.
- `signals`: señales analíticas.

Admite texto libre y filtros estructurados por RUT, `entity_id`, año/rango, región, comuna, tramo de ventas, trabajadores, actividad, tipo/subtipo de contribuyente, estado, señal, severidad, fechas y contadores de actividades/direcciones/señales.

La ejecución entrega `result.csv`, `result.json` y `query_metadata.json` como artifact de GitHub Actions.

## Almacenamiento

Los TXT/ZIP de origen y los Parquet analíticos pueden superar ampliamente los límites razonables de Git. Por ello:

- Git conserva código, reglas, tests, esquemas, documentación y salidas compactas.
- GitHub Actions descarga la fuente oficial y registra checksum SHA-256.
- La normalización se realiza por bloques.
- DuckDB consulta directamente los Parquet sin cargar toda la historia en memoria.
- Los resultados de consultas se publican como artifacts temporales.

No se requiere servidor externo en esta fase.

## Ejecución

```bash
python -m pip install -r requirements.txt
python -m pip install -e .
python -m radar_sii.pipeline
```

Consulta:

```bash
python -m radar_sii.query_job \
  --scope history \
  --text "construccion" \
  --filters-json '{"region":"Metropolitana","year_from":2020,"year_to":2024}' \
  --limit 1000
```

## Dashboard

`docs/` contiene una vista ejecutiva para GitHub Pages con cobertura, señales, distribución de tramos de ventas, regiones y trazabilidad de fuentes. El workflow mensual regenera las salidas compactas desde las fuentes oficiales.

En un repositorio nuevo puede ser necesario habilitar una vez **Settings -> Pages -> Build and deployment -> Source: GitHub Actions**.

## Integración futura

Radar SII permanece autónomo durante esta fase. La conexión posterior con otros radares se realizará mediante:

```text
RUT validado
    -> entity_id común
    -> nombre normalizado
    -> temporalidad
    -> territorio
    -> actividad económica
    -> evidence_links
```

Esto permitirá, por ejemplo, enriquecer un proveedor observado por Presupuesto Abierto o CGR con su historia SII sin confundir evidencia tributaria pública, señales analíticas e inferencias AML.
