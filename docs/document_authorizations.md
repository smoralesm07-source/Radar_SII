# Autorizaciones documentales observadas

Radar SII incorpora una dimensión adicional para registrar verificaciones de documentos tributarios específicos realizadas contra la consulta pública del Servicio de Impuestos Internos.

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

## Ingesta

`python -m radar_sii.document_authorizations --input observaciones.csv`

El insumo puede provenir de cualquier radar que materialice un documento identificable. Radar Presupuesto Abierto es un candidato natural porque su contrato de transacciones contempla `rut_beneficiario`, `numero_documento`, `fecha_documento`, `tipo_documento` y `folio`.

La ingesta sólo debe registrar respuestas obtenidas efectivamente del SII. No se deben fabricar fechas de autorización ni inferirlas desde la fecha de factura.

## Uso analítico

En Entity 360 se recomienda mostrar:

- última autorización documental observada;
- tipo y número del documento;
- antigüedad desde esa autorización;
- número de documentos autorizados observados;
- advertencia de cobertura parcial.

Este antecedente es contexto tributario. No constituye por sí solo una señal AML ni prueba actividad económica efectiva.
