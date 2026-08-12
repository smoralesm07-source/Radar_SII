# Radar SII v0.1.1

## Correcciones de producción

Esta versión se construyó después de perfilar los archivos oficiales reales del SII y corrige falsos positivos de cobertura que podían ocurrir aunque una descarga terminara técnicamente sin error.

1. La nómina anual 2020-2024 se procesa completa: cinco TXT, uno por año comercial.
2. Las direcciones procesan domicilios y sucursales, no sólo el miembro de mayor tamaño del ZIP.
3. Los alias canónicos corresponden a los encabezados reales publicados por SII.
4. Las fechas aceptan tanto ISO `YYYY-MM-DD` como formato SII `DD-MM-YYYY` sin reinterpretación ambigua.
5. `Tramo según ventas` utiliza la escala ordinal publicada `1..13`; `1` es sin información.
6. Se activa la Composición de Sociedades como `ownership_edges` con protección explícita del agregado `Personas Naturales`.
7. Cada búsqueda incorpora manifiesto de snapshots/checksums y metadata de calidad/cobertura.
8. El pipeline falla si no encuentra exactamente 2020, 2021, 2022, 2023 y 2024 en la historia anual.

## Nuevas señales longitudinales

- `WORKFORCE_DROP_STABLE_SALES`
- `MAIN_ACTIVITY_CHANGE`

Se mantienen las señales anteriores, recalibradas a la escala real de tramos SII.

## Preparación para integración

La identidad base permanece `ENT-RUT-{RUT_VALIDADO}` y las relaciones societarias entre personas jurídicas utilizan el mismo `entity_id`. Esto permite que una futura capa Entity Hub conecte Radar SII con Radar CGR y Radar Presupuesto Abierto preservando la procedencia de cada evidencia.
