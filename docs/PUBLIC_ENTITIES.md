# Maestro de entidades y servicios públicos — Radar SII

## Objetivo

Permitir que Radar SII reconozca explícitamente entidades del sector público chileno y las trate de forma diferenciada en análisis empresariales, AML/LA-FT, territoriales y de interoperabilidad.

La clasificación evita considerar automáticamente a una institución estatal como empresa privada solo porque posea RUT, actividades económicas o aparezca en una relación societaria/publicada.

## Fuentes oficiales

### ChileCompra / Mercado Público — universo amplio

El API público `BuscarComprador` entrega la lista de organismos públicos registrados en Mercado Público. Esta fuente se usa para construir el universo amplio de entidades estatales/compradoras.

Campos retenidos:

- código de organismo comprador;
- nombre oficial publicado;
- fuente y URL;
- tipo de entidad derivado de reglas explicables;
- identificador público canónico `PUB-CL-*`.

### DIPRES — referencia estricta

La Ley de Presupuestos 2026 y el catálogo institucional de DIPRES se usan como segunda evidencia para distinguir organismos observados en la estructura institucional/presupuestaria del Gobierno Central.

`is_public_service_strict=true` requiere coincidencia nominal normalizada contra esta referencia. El hecho de figurar en Mercado Público sí permite `is_public_entity=true`, pero no convierte automáticamente a la entidad en servicio público de la Administración Central.

## Identidad con Radar SII

El enlace con SII se realiza solo cuando el nombre oficial puede coincidir de forma **exacta, normalizada y unívoca** con la nómina pública de nombres de personas jurídicas del SII.

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
- `OTHER_PUBLIC_BUYER`

## Uso en consultas

El motor `Search Radar SII` admite el nuevo scope:

```text
public_entities
```

Y en los demás scopes pueden utilizarse:

```json
{"is_public_entity": true}
```

```json
{"is_public_service_strict": true}
```

```json
{"public_entity_type": "MUNICIPALITY"}
```

Las columnas públicas son añadidas a resultados de entidades, historia, actividades, direcciones, señales y relaciones cuando existe un `entity_id` asociado.

## Regla AML / analítica

La calidad de entidad pública es **contexto institucional**, no una señal de riesgo. Debe usarse para:

1. separar sector público de universo empresarial privado;
2. identificar organismos públicos como contrapartes en cruces con Presupuesto Abierto/CGR;
3. construir análisis de concentración de proveedores por servicio público;
4. evitar falsos positivos derivados de comparar instituciones fiscales con empresas privadas;
5. enriquecer el Entity Hub y el Intelligence Fusion Layer con tipo institucional explicable;
6. mantener trazabilidad hasta la fuente oficial que sustenta la clasificación.

## Actualización

Workflow: `Maestro entidades públicas`.

- ejecución manual disponible;
- actualización mensual automática;
- descarga nuevamente la nómina SII de nombres para resolver RUT de forma conservadora;
- actualiza `config/public_entities_registry.csv`;
- publica `docs/data/public_entities_summary.json`;
- conserva artifacts de cada corrida durante 30 días.

La fuente ChileCompra es más amplia que el concepto jurídico estricto de servicio público. Por diseño ambos conceptos permanecen separados en el modelo.
