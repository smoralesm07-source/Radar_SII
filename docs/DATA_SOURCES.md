# Fuentes de datos — Radar SII v0.1

## Núcleo granular

| ID | Fuente | Cobertura observable | Actualización publicada | Uso |
|---|---|---|---|---|
| `sii_company_year` | Nómina de empresas personas jurídicas | Años comerciales 2020-2024 | noviembre 2025 | historia anual de tramo de ventas, trabajadores, región, rubro, actividad, fechas, tipo/subtipo y capital propio tributario |
| `sii_names_current` | Nómina de Razón Social | snapshot vigente | agosto 2026 | razón social, inicio de actividades, término de giro |
| `sii_activities_current` | Nómina de actividades económicas | actividades vigentes al snapshot | agosto 2026 | códigos/glosas y amplitud de actividades |
| `sii_addresses_history` | Nómina de direcciones históricas | casa matriz/sucursales vigentes y no vigentes al snapshot | agosto 2026 | comuna, región, cambios y amplitud territorial según campos publicados |

Página oficial: `https://www.sii.cl/sobre_el_sii/nominapersonasjuridicas.html`

## Fuentes SII complementarias identificadas

El SII también publica estadísticas abiertas de empresas para 2005-2024, con número de empresas, ventas, trabajadores y remuneraciones desagregadas por geografía, actividad y tamaño, además de estadísticas de primera inscripción de actividades y términos de giro. Estas fuentes son candidatas para una capa de **benchmark/peer calibration** porque permiten comparar una señal individual con el comportamiento agregado del sector/comuna sin reemplazar el hecho granular.

- Estadísticas de empresas: `https://www.sii.cl/sobre_el_sii/estadisticas_de_empresas.html`
- Inicio de actividades y términos de giro: `https://www.sii.cl/sobre_el_sii/estadisticas_inicio_de_actividades.html`

## Reglas de interpretación

- SII calcula las ventas anuales mediante un algoritmo basado en códigos de F22/F29; no deben tratarse como monto económico exacto.
- Los trabajadores se contabilizan por empleador y pueden repetirse entre empleadores.
- La dotación se asocia al domicilio/casa matriz de la empresa, no al lugar físico donde trabaja cada persona.
- Las cifras pueden variar por rectificaciones o fiscalización.
- El radar registra `snapshot`, fecha de descarga y SHA-256 para reproducibilidad.
