-- Contrato lógico compatible con los demás radares. Los Parquet son la implementación v0.1.
CREATE TABLE IF NOT EXISTS source_snapshots (
  snapshot_id VARCHAR PRIMARY KEY, source_id VARCHAR, source_url VARCHAR, sha256 VARCHAR,
  bytes BIGINT, downloaded_at TIMESTAMP, etag VARCHAR, last_modified VARCHAR
);
CREATE TABLE IF NOT EXISTS legal_entities (
  entity_id VARCHAR PRIMARY KEY, rut VARCHAR UNIQUE, legal_name VARCHAR, legal_name_norm VARCHAR,
  activity_start_date DATE, termination_date DATE, current_status VARCHAR, source_snapshot_id VARCHAR
);
CREATE TABLE IF NOT EXISTS company_year (
  record_id VARCHAR PRIMARY KEY, entity_id VARCHAR, commercial_year INTEGER, sales_band VARCHAR,
  workers BIGINT, region VARCHAR, economic_sector VARCHAR, economic_subsector VARCHAR,
  main_activity VARCHAR, taxpayer_type VARCHAR, taxpayer_subtype VARCHAR,
  positive_equity_band VARCHAR, negative_equity_band VARCHAR, activity_start_date DATE,
  termination_date DATE, termination_type VARCHAR, source_snapshot_id VARCHAR
);
CREATE TABLE IF NOT EXISTS entity_activities (
  activity_record_id VARCHAR PRIMARY KEY, entity_id VARCHAR, activity_code VARCHAR,
  activity_name VARCHAR, activity_category VARCHAR, activity_status VARCHAR, source_snapshot_id VARCHAR
);
CREATE TABLE IF NOT EXISTS entity_addresses (
  address_record_id VARCHAR PRIMARY KEY, entity_id VARCHAR, address_type VARCHAR, street VARCHAR,
  street_number VARCHAR, commune VARCHAR, region VARCHAR, address_status VARCHAR, source_snapshot_id VARCHAR
);
CREATE TABLE IF NOT EXISTS evidence_links (
  evidence_id VARCHAR PRIMARY KEY, entity_id VARCHAR, source_id VARCHAR, source_url VARCHAR,
  source_record_id VARCHAR, evidence_type VARCHAR, confidence VARCHAR, is_inference BOOLEAN DEFAULT FALSE
);
