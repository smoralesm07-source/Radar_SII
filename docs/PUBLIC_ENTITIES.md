# Maestro de entidades y servicios públicos — Radar SII

## Objetivo

Permitir que Radar SII reconozca explícitamente entidades del sector público chileno y las trate de forma diferenciada en análisis empresariales, AML/LA-FT, territoriales y de interoperabilidad.

La clasificación evita considerar automáticamente a una institución estatal como empresa privada solo porque posea RUT, actividades económicas o aparezca en una relación societaria/publicada.

## Fuentes oficiales

### Gob.cl — nómina estricta de Servicios Públicos

La página oficial `Instituciones` de Gob.cl publica una sección explícita **Servicios Públicos**, separada de ministerios y de regiones/municipios. Esta sección define `is_public_service_strict=true` y constituye la referencia principal para responder si una entidad forma parte de la nómina de servicios públicos del Gobierno de Chile.

### ChileCompra / Mercado Público — universo amplio de compradores públicos

El API público `BuscarComprador` aporta el universo operativo de organismos compradores del Estado. Figurar aquí permite reconocer una entidad como pública, pero no implica por sí solo que sea un servicio público estricto.

### Datos.gob / Secretaría de Gobierno Digital — directorio institucional complementario

El directorio de instituciones de Datos.gob recupera entidades públicas que pueden no estar representadas de igual forma en Mercado Público y refuerza la identidad institucional cuando varias fuentes coinciden.

### DIPRES — corroboración institucional/presupuestaria

La Ley de Presupuestos y el catálogo institucional de DIPRES se conservan como evidencia adicional del Gobierno Central. `dipres_reference_match=true` corrobora presencia institucional/presupuestaria, pero ya no define por sí mismo `is_public_service_strict`.

## Identidad con Radar SII

El enlace con SII se realiza solo cuando el nombre oficial coincide de forma **exacta, normalizada y unívoca** con la nómina pública de nombres de personas jurídicas del SII.

Cuando existe coincidencia:

```text
rut -> entity_id = ENT-RUT-{RUT}
```

Cuando no existe una coincidencia suficientemente segura:

```text
public_entity_id = PUB-CL-{HASH}
rut = vacío
entity_id = vacío
sii_match_method = NO_RUT_MATCH
```

No se utiliza fuzzy matching automático para asignar RUT. Los organismos sin match permanecen en el maestro y pueden ser enriquecidos posteriormente con una fuente oficial que publique su identidad tributaria.

## Variables de análisis

- `is_public_entity`
- `is_public_service_strict`
- `public_entity_type`
- `public_entity_id`
- `public_entity_name`
- `source_system`
- `source_code`
- `gob_cl_reference_match`
- `chilecompra_reference_match`
- `datos_gob_reference_match`
- `dipres_reference_match`
- `sii_match_method`
- `sii_match_confidence`

Tipos iniciales:

- `MUNICIPALITY`
- `REGIONAL_GOVERNMENT`
- `PRESIDENTIAL_DELEGATION`
- `PUBLIC_HEALTH`
- `MINISTRY_OR_SUBSECRETARIAT`
- `SUPERVISOR_OR_REGULATOR`
- `DEFENCE_OR_PUBLIC_SECURITY`
- `STATE_COMPANY_OR_PUBLIC_CORPORATION`
- `STATE_HIGHER_EDUCATION`
- `PUBLIC_SERVICE_OR_AGENCY`
- `OTHER_PUBLIC_ENTITY`

## Uso en consultas

El motor `Search Radar SII` admite el scope `public_entities` y, en los demás scopes, filtros como:

```json
{"is_public_entity": true}
```

```json
{"is_public_service_strict": true}
```

```json
{"public_entity_type": "MUNICIPALITY"}
```

Los filtros públicos se aplican antes del límite de resultados para no sesgar la consulta sobre el universo SII.

## Regla AML / analítica

La calidad de entidad pública es **contexto institucional, no una señal de riesgo**. El pipeline conserva las señales SII originales para trazabilidad, pero añade:

- `analysis_population = PUBLIC_ENTITY_CONTEXT`;
- `business_ranking_eligible = false` por defecto;
- `signal_applicability = CONTEXT_ONLY_PUBLIC_ENTITY` en señales asociadas a entidades públicas.

Esto permite separar el análisis de instituciones estatales de los rankings empresariales privados sin borrar evidencia.

## Interoperabilidad

El contrato Fusion v1.1 expone `public_entities_registry` como `EntityContext`. El bundle público de Radar SII enriquece `entity_search.parquet` con las banderas públicas cuando existe `entity_id` y conserva el maestro completo para organismos sin RUT resuelto.

## Actualización

Workflow: `Maestro entidades públicas`.

- ejecución manual disponible;
- actualización mensual automática;
- vuelve a consultar Gob.cl, ChileCompra, Datos.gob y DIPRES;
- descarga la nómina SII de nombres para resolver RUT de forma conservadora;
- actualiza `config/public_entities_registry.csv`;
- publica `docs/data/public_entities_summary.json`;
- falla si la extracción Gob.cl cae a un volumen incompatible con la nómina vigente, evitando publicar silenciosamente una lista parcial.

Las cuatro fuentes tienen alcances distintos y sus evidencias permanecen separadas y trazables en el modelo.
