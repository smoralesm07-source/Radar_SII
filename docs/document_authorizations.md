# Autorizaciones documentales observadas

Radar SII incorpora una dimensión adicional para registrar verificaciones de documentos tributarios específicos realizadas contra el Servicio de Impuestos Internos.

## Regla de interpretación

La consulta pública `Consultar timbraje de documentos` verifica un documento concreto usando RUT, tipo y número de documento. Cuando el documento está autorizado, el SII informa la fecha de autorización.

Por esta razón, Radar SII utiliza la expresión **última autorización documental observada**. No se declara que sea el **último timbraje absoluto** del contribuyente, salvo que en el futuro exista una fuente con cobertura completa del historial.

Ausencia de registros tampoco significa ausencia de timbrajes: significa que Radar SII todavía no dispone de un documento verificable para esa entidad.

## Contrato

El archivo `schemas/004_document_authorizations.sql` agrega `document_authorizations` y la vista `latest_document_authorization_observed`.

Campos principales:

- `entity_id` / `rut`: identidad canónica.
- `document_type_code` / `document_type_name`: tipo documental.
- `document_number`: folio o número verificado.
- `document_date`: fecha del documento cuando la fuente de origen la informa.
- `authorization_date`: fecha que devuelve el SII para el documento autorizado.
- `authorization_status`: `AUTHORIZED`, `NOT_AUTHORIZED` o `UNKNOWN`.
- `observed_at`: momento de la verificación.
- `source_response_sha256`: huella de la respuesta, sin almacenar texto innecesario.
- `evidence_id`: identificador determinístico para trazabilidad.

## Puente con documentos observados en otros radares

Radar Presupuesto Abierto es un productor natural de candidatos porque su contrato de transacciones contempla `rut_beneficiario`, `numero_documento`, `fecha_documento`, `tipo_documento` y `folio`.

El módulo `radar_sii.cmsp_bridge` convierte esos documentos candidatos al formato oficial de la Consulta Masiva Situación de Proveedores (CMSP):

```bash
python -m radar_sii.cmsp_bridge prepare \
  --input transacciones_candidatas.parquet \
  --out .radar_sii/cmsp/document_candidates.txt
```

El archivo generado contiene como máximo 10.000 registros y usa el contrato:

`RUT_BODY;DV;CODIGO_DOCUMENTO;NUMERO_DOCUMENTO;AAAAMMDD`

Los tipos documentales desconocidos no se adivinan: quedan fuera del lote para revisión.

## Consulta SII y retorno gobernado

La CMSP requiere autenticación del contribuyente en el SII y tiene restricciones operacionales propias. Radar SII **no almacena ni automatiza credenciales tributarias**. El archivo preparado se consulta dentro del canal autenticado oficial del SII y el resultado descargado se normaliza después:

```bash
python -m radar_sii.cmsp_bridge parse \
  --input respuesta_sii.txt \
  --out .radar_sii/silver/sii_document_authorizations.parquet
```

También es posible normalizar observaciones individuales ya verificadas:

```bash
python -m radar_sii.document_authorizations --input observaciones.csv
```

La ingesta sólo registra respuestas obtenidas efectivamente del SII. No se fabrican fechas de autorización ni se infieren desde la fecha del documento.

## Uso analítico

Entity 360 consume la última autorización documental observada mediante una vista protegida por RLS. Cuando existe evidencia, muestra:

- fecha de autorización;
- antigüedad desde esa autorización;
- tipo y número del documento;
- fecha del documento cuando está materializada;
- cantidad de documentos autorizados observados;
- evidencia y momento de consulta.

Cuando no existe observación, la ficha declara **sin observación** y no lo interpreta como ausencia de timbraje.

Este antecedente es contexto tributario. No constituye por sí solo una señal AML ni prueba actividad económica efectiva.
