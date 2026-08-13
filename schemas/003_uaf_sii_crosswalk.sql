-- Maestro analítico UAF <-> ACTECO SII v0.1.
-- Fuente versionada: config/uaf_sii_crosswalk.csv
-- IMPORTANTE: una coincidencia ACTECO es una señal de compatibilidad sectorial;
-- no acredita por sí sola la calidad jurídica ni la inscripción como Sujeto Obligado UAF.

CREATE OR REPLACE VIEW uaf_sii_crosswalk AS
SELECT
  CAST(uaf_sector_id AS INTEGER) AS uaf_sector_id,
  TRIM(uaf_sector) AS uaf_sector,
  NULLIF(TRIM(CAST(sii_acteco AS VARCHAR)), '') AS sii_acteco,
  NULLIF(TRIM(sii_glosa), '') AS sii_glosa,
  TRIM(tipo_equivalencia) AS tipo_equivalencia,
  TRIM(confianza) AS confianza,
  TRIM(uso_radar) AS uso_radar,
  TRIM(fuente_complementaria_sugerida) AS fuente_complementaria_sugerida
FROM read_csv(
  'config/uaf_sii_crosswalk.csv',
  delim = ';',
  header = true,
  all_varchar = true
);

CREATE OR REPLACE VIEW entity_uaf_activity_candidates AS
SELECT
  ea.entity_id,
  ea.activity_code,
  ea.activity_name,
  ea.activity_registration_date,
  ea.activity_status,
  cw.uaf_sector_id,
  cw.uaf_sector,
  cw.tipo_equivalencia,
  cw.confianza,
  cw.uso_radar,
  cw.fuente_complementaria_sugerida,
  ea.source_snapshot_id
FROM entity_activities ea
JOIN uaf_sii_crosswalk cw
  ON LPAD(TRIM(CAST(ea.activity_code AS VARCHAR)), 6, '0') = cw.sii_acteco
WHERE cw.sii_acteco IS NOT NULL;

CREATE OR REPLACE VIEW uaf_sector_candidate_summary AS
SELECT
  uaf_sector_id,
  uaf_sector,
  tipo_equivalencia,
  confianza,
  uso_radar,
  COUNT(DISTINCT entity_id) AS candidate_entities
FROM entity_uaf_activity_candidates
GROUP BY 1,2,3,4,5;
