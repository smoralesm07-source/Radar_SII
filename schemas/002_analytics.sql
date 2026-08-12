CREATE TABLE IF NOT EXISTS derived_features (
  feature_id VARCHAR PRIMARY KEY, entity_id VARCHAR, commercial_year INTEGER, feature_name VARCHAR,
  observed_value VARCHAR, comparator VARCHAR, feature_version VARCHAR
);
CREATE TABLE IF NOT EXISTS risk_signals (
  signal_id VARCHAR PRIMARY KEY, entity_id VARCHAR, signal_type VARCHAR, period VARCHAR,
  severity VARCHAR, severity_score INTEGER, confidence VARCHAR, why_flagged VARCHAR,
  recommended_checks VARCHAR, source_record_id VARCHAR, generated_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_company_year_entity_year ON company_year(entity_id, commercial_year);
CREATE INDEX IF NOT EXISTS idx_entity_activities_entity ON entity_activities(entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_addresses_entity ON entity_addresses(entity_id);
CREATE INDEX IF NOT EXISTS idx_risk_signals_entity ON risk_signals(entity_id);
