# Radar SII

Radar OSINT para transformar información pública del **Servicio de Impuestos Internos de Chile (SII)** en datos empresariales históricos, trazables y reutilizables para inteligencia de riesgo con enfoque AML/LA-FT.

> Una señal estadística, cambio registral o inconsistencia aparente no acredita por sí sola lavado de activos, evasión, delito ni irregularidad. El sistema prioriza revisión y conserva la evidencia oficial de origen.

## v0.1.1 — Historia empresarial, domicilios y relaciones societarias publicadas

La versión 0.1.1 corrige la ingestión multiarquivo del SII y utiliza **todos los archivos anuales 2020, 2021, 2022, 2023 y 2024** contenidos en la nómina de empresas personas jurídicas. Se complementa con las nóminas registrales publicadas en **agosto de 2026** y con la **Composición de Sociedades** publicada por SII en noviembre de 2025.

La regla de arquitectura es la misma usada por Radar CGR y Radar Presupuesto Abierto:

```text
SOURCE_SNAPSHOT -> SOURCE_FACT -> CANONICAL_ENTITY -> DERIVED_FEATURE -> RISK_SIGNAL -> EVIDENCE / LINEAGE
```

Los hechos de fuente nunca se sustituyen por inferencias analíticas. Cada descarga registra URL, SHA-256, tamaño, fecha de descarga, metadatos HTTP, cobertura declarada y miembros exactos del ZIP utilizados.

## Cobertura de fuentes

### Historia anual granular 2020-2024

Por RUT y año comercial se conservan, cuando están publicados:

- tramo SII según ventas, código ordinal 1-13;
- número de trabajadores dependientes;
- región, provincia y comuna;
- rubro y subrubro económico;
- actividad económica principal;
- fecha de inicio de actividades vigentes;
- fecha de primera inscripción de actividad;
- fecha y tipo de término de giro;
- tipo y subtipo de contribuyente;
- tramos de capital propio tributario positivo y negativo;
- régimen de renta presunta y otros regímenes publicados.

**Interpretación crítica:** el tramo de ventas es una clasificación tributaria calculada por SII y no un monto exacto de ventas. El código `1` significa `Sin información`; por diseño nunca se utiliza como base de un salto de ventas. La dotación publicada se asocia al empleador/casa matriz y debe interpretarse según industria y modelo operativo.

### Snapshot registral actual

- razón social;
- código de subtipo de contribuyente;
- fecha vigente de inicio de actividades;
- fecha vigente de término de giro;
- actividades económicas registradas, fecha, afectación IVA y categoría tributaria;
- domicilios y sucursales históricas, con vigencia, fecha, comuna y región.

### Composición de Sociedades

Se modelan relaciones publicadas por SII como `OWNERSHIP_AS_PUBLISHED`:

- sociedad / `entity_id`;
- tipo y subtipo societario;
- socio persona jurídica cuando existe RUT válido;
- porcentaje publicado cuando está disponible;
- agrupación `PERSONAS_NATURALES` cuando SII publica personas naturales de forma agregada.

**No se infieren beneficiarios finales ni identidades naturales.** `Personas Naturales` se conserva expresamente como agregado de fuente y jamás se transforma en una persona individual.

## Identidad interoperable

Para una persona jurídica con RUT formalmente válido:

```text
entity_id = ENT-RUT-{RUT_NORMALIZADO}
```

La clave es neutral al rol. La misma entidad puede aparecer posteriormente como proveedor/receptor en Radar Presupuesto Abierto, entidad/proveedor en Radar CGR o sociedad/socio persona jurídica en Radar SII.

## Tablas principales

- `source_snapshots`
- `legal_entities`
- `company_year`
- `entity_activities`
- `entity_addresses`
- `ownership_edges`
- `derived_features`
- `risk_signals`
- `evidence_links`

Los Parquet productivos correspondientes son regenerables desde los archivos oficiales y no se versionan en Git.

## Inteligencia temporal y señales v0.1.1

Las reglas son determinísticas, explicables y recalculables:

- `SALES_BAND_JUMP`: aumento de al menos tres tramos entre años consecutivos con información.
- `HIGH_SALES_LOW_WORKFORCE`: tramo de gran empresa con hasta dos trabajadores informados.
- `RECENT_START_HIGH_SALES`: empresa de hasta dos años desde inicio publicado que alcanza tramo de gran empresa.
- `HIGH_SALES_NEGATIVE_EQUITY`: tramo alto coexistiendo con tramo de capital propio tributario negativo.
- `WORKFORCE_DROP_STABLE_SALES`: dotación cae al 20% o menos, partiendo desde al menos diez trabajadores, sin disminución del tramo de ventas.
- `MAIN_ACTIVITY_CHANGE`: cambio de actividad económica principal entre años consecutivos.
- `REGION_CHANGE`: cambio de región entre años consecutivos.
- `ACTIVITY_BREADTH`: seis o más actividades económicas vigentes/publicadas.
- `ADDRESS_HISTORY_BREADTH`: amplitud relevante de domicilios o regiones publicadas.
- `REACTIVATION_PATTERN`: término de giro histórico coexistiendo con estado activo en la nómina actual.

Una señal **prioriza revisión**. No constituye un hallazgo tributario, penal ni AML.

## Motor de búsqueda

Workflow: **Actions -> Search Radar SII -> Run workflow**.

Ámbitos:

- `entities`: ficha consolidada por RUT;
- `history`: trayectoria empresa-año 2020-2024;
- `activities`: actividades económicas actuales;
- `addresses`: domicilios y sucursales históricas;
- `ownership`: relaciones societarias publicadas;
- `signals`: señales analíticas.

Filtros disponibles incluyen RUT, `entity_id`, año/rango, región, comuna, tramo de ventas, trabajadores, actividad, tipo/subtipo, estado, fechas, señal/severidad, número de actividades/direcciones/señales, socio persona jurídica, tipo de socio, tipo/subtipo societario y porcentaje de participación.

Cada consulta entrega:

- `result.csv`
- `result.json`
- `query_metadata.json`
- `snapshot_manifest.json`
- `source_catalog.json`
- `coverage.json`
- `quality.json`

De esta forma, una búsqueda queda vinculada a los archivos SII exactos y sus checksums.

## Almacenamiento

Los ZIP/TXT oficiales y Parquet analíticos son demasiado grandes para versionarlos razonablemente en Git. Por ello:

- Git conserva código, reglas, tests, esquemas, documentación y metadata compacta;
- GitHub Actions descarga las fuentes oficiales y calcula SHA-256;
- la normalización se realiza por bloques;
- DuckDB consulta los Parquet sin cargar toda la historia en memoria;
- consultas y builds completos se entregan como artifacts temporales.

No se requiere servidor externo en esta etapa.

## Ejecución

```bash
python -m pip install -r requirements.txt
python -m pip install -e .
python -m radar_sii.pipeline
```

Consulta por historia:

```bash
python -m radar_sii.query_job \
  --scope history \
  --filters-json '{"rut":"76086428-5","year_from":2020,"year_to":2024}' \
  --limit 1000
```

Consulta de relaciones societarias:

```bash
python -m radar_sii.query_job \
  --scope ownership \
  --filters-json '{"partner_rut":"76086428-5"}' \
  --limit 1000
```

## Calidad y controles de producción

El pipeline falla deliberadamente si no observa exactamente los años esperados `2020-2024`. También informa:

- cobertura de RUT/`entity_id`;
- duplicados entidad-año;
- cobertura de ventas, trabajadores, fechas, territorio y actividad;
- cobertura de códigos/glosas de actividades;
- vigencia y fechas de domicilios;
- relaciones societarias PJ vs agregado de personas naturales;
- cobertura y límites de porcentajes publicados.

Esto evita que una descarga técnicamente exitosa sea considerada correcta si perdió miembros internos del ZIP o columnas relevantes.

## Dashboard y actualización

`docs/` contiene una vista ejecutiva para GitHub Pages. El workflow mensual reconstruye metadata y dashboard desde las fuentes oficiales.

En un repositorio nuevo debe habilitarse una vez **Settings -> Pages -> Build and deployment -> Source: GitHub Actions**.

## Integración futura de radares

Radar SII permanece autónomo en esta fase. La capa común posterior utilizará:

```text
RUT validado
  -> entity_id común
  -> nombre normalizado
  -> período
  -> territorio
  -> actividad económica
  -> ownership_edges
  -> evidence_links
```

Así, un proveedor detectado en Presupuesto Abierto o CGR podrá enriquecerse con trayectoria tributaria pública SII y relaciones societarias publicadas sin confundir hechos de fuente con señales o inferencias AML.
