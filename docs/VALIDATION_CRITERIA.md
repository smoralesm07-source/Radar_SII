# Criterios de aceptación productiva — Radar SII v0.1.1

La versión sólo se considera validada sobre fuentes oficiales si el build completo cumple simultáneamente:

- historia anual observada exactamente en 2020, 2021, 2022, 2023 y 2024;
- más de 4 millones de hechos `company_year`;
- cero duplicados de la llave `entity_id + commercial_year`;
- más de un millón de entidades buscables en la ficha consolidada;
- carga efectiva de la nómina de composición societaria;
- más de 50% de cobertura de fecha vigente de inicio de actividades en la nómina de razón social;
- generación exitosa de `quality.json`, `coverage.json`, `dashboard.json` y manifiesto de snapshots.

Los tests unitarios y el test de integración DuckDB deben estar verdes antes de ejecutar esta validación de volumen.
