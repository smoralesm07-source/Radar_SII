# Changelog

## 0.1.2 — Autorizaciones documentales observadas

- Agrega contrato `document_authorizations` y vista de última autorización documental observada.
- Incorpora normalizador trazable de respuestas SII con hash SHA-256 y evidencia determinística.
- Agrega puente CMSP para preparar hasta 10.000 documentos candidatos y normalizar el archivo de respuesta oficial.
- Mantiene la semántica `LATEST_OBSERVED_AUTHORIZATION_NOT_ABSOLUTE_LAST_TIMBRAJE`.
- Ausencia de observación no se interpreta como ausencia de timbraje.
- No se almacenan ni automatizan credenciales tributarias del SII.
- Entity 360 puede consumir la dimensión mediante la capa Fusion/Supabase protegida por RLS.

## 0.1.1 — Historia empresarial, domicilios y relaciones societarias

- Historia anual 2020–2024.
- Snapshot registral actual.
- Actividades, domicilios y composición de sociedades.
- Señales temporales y cobertura trazable.
