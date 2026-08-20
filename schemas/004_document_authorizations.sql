-- Radar SII · autorizaciones/timbrajes documentales observados
--
-- Este contrato NO declara el universo completo de timbrajes de un contribuyente.
-- La consulta pública del SII permite verificar un documento específico y, cuando
-- está autorizado, informa la fecha de autorización. Por ello la semántica
-- gobernada es "última autorización documental observada", no "último timbraje
-- absoluto", salvo que una fuente posterior entregue cobertura completa.

CREATE TABLE IF NOT EXISTS document_authorizations (
  authorization_record_id VARCHAR PRIMARY KEY,
  entity_id VARCHAR NOT NULL,
  rut VARCHAR NOT NULL,
  document_type_code VARCHAR,
  document_type_name VARCHAR,
  document_number VARCHAR NOT NULL,
  document_date DATE,
  authorization_date DATE,
  authorization_status VARCHAR NOT NULL,
  observation_kind VARCHAR NOT NULL DEFAULT 'SPECIFIC_DOCUMENT_VERIFICATION',
  source_system VARCHAR NOT NULL DEFAULT 'SII_CVC_VDC',
  source_url VARCHAR NOT NULL DEFAULT 'https://zeus.sii.cl/cvc/vdc/index.html',
  source_response_sha256 VARCHAR,
  source_snapshot_id VARCHAR,
  evidence_id VARCHAR,
  observed_at TIMESTAMP NOT NULL
);

CREATE VIEW IF NOT EXISTS latest_document_authorization_observed AS
SELECT * EXCLUDE (rn)
FROM (
  SELECT *,
         row_number() OVER (
           PARTITION BY entity_id
           ORDER BY authorization_date DESC NULLS LAST, observed_at DESC
         ) AS rn
  FROM document_authorizations
  WHERE authorization_status = 'AUTHORIZED'
)
WHERE rn = 1;
