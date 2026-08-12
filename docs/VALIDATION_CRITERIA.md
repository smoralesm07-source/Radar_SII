# Criterios de aceptación productiva — Radar SII v0.1.1

La versión sólo se considera validada sobre fuentes oficiales si el build completo cumple simultáneamente:

- historia anual observada exactamente en 2020, 2021, 2022, 2023 y 2024;
- más de 4 millones de filas en el hecho fuente anual;
- más de 4 millones de hechos canónicos `entity_id + commercial_year`;
- cero duplicados en la vista canónica `entity_id + commercial_year`;
- cero grupos entity-year con conflicto en ventas, trabajadores, territorio, actividad, tipo/subtipo, capital u otros campos empresariales;
- cualquier duplicidad de fuente limitada a variantes de `fecha término de giro` queda preservada en `sii_company_year_source.parquet`, marcada con `termination_date_conflict` y sus valores publicados, sin escoger silenciosamente una fecha canónica;
- más de un millón de entidades buscables en la ficha consolidada;
- carga efectiva de la nómina de composición societaria;
- más de 50% de cobertura de fecha vigente de inicio de actividades en la nómina de razón social;
- generación exitosa de `quality.json`, `coverage.json`, `dashboard.json` y manifiesto de snapshots.

Los tests unitarios y el test de integración DuckDB deben estar verdes antes de ejecutar esta validación de volumen.

## Política de conflicto

`SOURCE_FACT` y `CANONICAL_FACT` se mantienen separados. Un conflicto empresarial estable provoca fallo del pipeline. Una discrepancia limitada a fecha de término de giro se conserva como evidencia de calidad de fuente y se excluye de la fecha canónica hasta contar con un criterio de resolución explícito; el radar no elige un valor arbitrariamente.
