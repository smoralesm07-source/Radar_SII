# Fuentes de datos — Radar SII v0.1.1

## Núcleo granular

| ID | Fuente | Cobertura observable | Actualización publicada | Uso |
|---|---|---|---|---|
| `sii_company_year` | Nómina de empresas personas jurídicas | años comerciales 2020-2024 | noviembre 2025 | trayectoria anual de ventas, trabajadores, territorio, actividad, fechas, tipo/subtipo y capital propio tributario |
| `sii_names_current` | Nómina de Razón Social | snapshot vigente | mayo 2026 | razón social, código de subtipo, inicio de actividades y término de giro |
| `sii_activities_current` | Nómina de actividades económicas | actividades vigentes al snapshot | mayo 2026 | código/glosa, fecha de inscripción, afectación IVA y categoría tributaria |
| `sii_addresses_history` | Nómina de direcciones históricas | domicilios y sucursales vigentes/no vigentes | mayo 2026 | vigencia, fecha, calle, comuna, región e historia territorial |
| `sii_ownership_current` | Composición de Sociedades | composición registrada vigente/válida | noviembre 2025 | relaciones sociedad-socio PJ y agregado explícito de personas naturales |

Página oficial del núcleo registral: `https://www.sii.cl/sobre_el_sii/nominapersonasjuridicas.html`

## Estructura real de los ZIP

La inspección de producción confirmó que las fuentes son multiarquivo y el pipeline selecciona miembros explícitos:

### Empresas 2020-2024

- `PUB_EMPRESAS_PJ_2020.txt`
- `PUB_EMPRESAS_PJ_2021.txt`
- `PUB_EMPRESAS_PJ_2022.txt`
- `PUB_EMPRESAS_PJ_2023.txt`
- `PUB_EMPRESAS_PJ_2024.txt`

El pipeline valida que los cinco años estén presentes después de normalizar; una pérdida silenciosa de uno o más archivos provoca error de cobertura.

### Razón social

Se ingiere `PUB_NOMBRES_PJ.txt`. El catálogo auxiliar de códigos de tipo/subtipo puede incorporarse en una versión posterior como dimensión de referencia.

### Direcciones

Se ingieren conjuntamente:

- `PUB_NOM_DOMICILIO.txt`
- `PUB_NOM_SUCURSAL.txt`

Esto evita reducir el historial territorial sólo al archivo más grande del ZIP.

## Composición de Sociedades

Fuente oficial: `https://www.sii.cl/sobre_el_sii/composicion_sociedades.html`

El archivo observado contiene:

- RUT de sociedad;
- DV de sociedad;
- tipo y subtipo societario;
- RUT/DV de socio cuando corresponde a una persona jurídica identificada;
- `ID Personas Naturales` cuando la fuente agrupa personas naturales;
- porcentaje de participación cuando SII lo publica.

Reglas obligatorias del radar:

1. `Personas Naturales` se almacena como `NATURAL_PERSONS_AGGREGATE`.
2. No se crea RUT, nombre, persona ni beneficiario final individual a partir de ese agregado.
3. Una relación PJ se crea sólo si el RUT del socio supera validación formal.
4. La participación ausente se conserva como ausente; nunca se imputa.
5. `OWNERSHIP_AS_PUBLISHED` describe una relación publicada por SII y no una conclusión de control efectivo o beneficiario final.

## Interpretación de variables anuales

- `Tramo según ventas` es un código ordinal SII `1..13`.
- `1` corresponde a `Sin información` y no se considera un tramo de venta bajo para cálculo de variaciones.
- SII estima ventas anuales usando información tributaria; el radar no las convierte en montos exactos.
- Los trabajadores se cuentan por empleador y pueden repetirse entre empleadores.
- La dotación/localización puede asociarse a casa matriz y no al lugar efectivo de trabajo.
- Rectificaciones o procesos de fiscalización pueden modificar cifras publicadas posteriormente.

## Fuentes complementarias candidatas v0.2

El SII publica estadísticas agregadas de empresas para 2005-2024 y estadísticas de inicio/término. Se reservan para `PEER_BASELINE`, con el objetivo de comparar una entidad contra su sector, tamaño y territorio sin mezclar el benchmark agregado con el hecho granular.

También existe la consulta pública de Situación Tributaria de Terceros. Se considera candidata para enriquecimiento **puntual por RUT**, no para scraping masivo del radar.

## Trazabilidad

Por cada descarga se registra:

- `source_id`;
- URL fuente y página oficial;
- cobertura y actualización declarada;
- SHA-256;
- bytes;
- `downloaded_at`;
- `ETag` y `Last-Modified` cuando existen;
- miembros internos seleccionados del ZIP;
- versión de normalización.

Los archivos masivos no se versionan en Git; la metadata sí acompaña cada build y consulta.
