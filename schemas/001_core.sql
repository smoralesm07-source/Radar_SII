-- Contrato lógico compatible con Radar CGR y Radar Presupuesto Abierto.
-- Los Parquet/DuckDB son la implementación productiva v0.1.1.

CREATE TABLE IF NOT EXISTS source_snapshots (
  snapshot_id VARCHAR PRIMARY KEY,
  source_id VARCHAR,
  source_url VARCHAR,
  official_page VARCHAR,
  sha256 VARCHAR,
  bytes BIGINT,
  downloaded_at TIMESTAMP,
  etag VARCHAR,
  last_modified VARCHAR,
  published_update VARCHAR,
  coverage VARCHAR,
  normalization_version VARCHAR,
  selected_members JSON
);

CREATE TABLE IF NOT EXISTS legal_entities (
  entity_id VARCHAR PRIMARY KEY,
  rut VARCHAR UNIQUE,
  legal_name VARCHAR,
  legal_name_norm VARCHAR,
  taxpayer_subtype_code VARCHAR,
  activity_start_date DATE,
  termination_date DATE,
  current_status VARCHAR,
  source_snapshot_id VARCHAR
);

CREATE TABLE IF NOT EXISTS company_year (
  record_id VARCHAR PRIMARY KEY,
  entity_id VARCHAR,
  commercial_year INTEGER,
  sales_band VARCHAR,
  sales_band_code INTEGER,
  workers BIGINT,
  region VARCHAR,
  province VARCHAR,
  commune VARCHAR,
  economic_sector VARCHAR,
  economic_subsector VARCHAR,
  main_activity VARCHAR,
  taxpayer_type VARCHAR,
  taxpayer_subtype VARCHAR,
  positive_equity_band VARCHAR,
  negative_equity_band VARCHAR,
  activity_start_date DATE,
  first_activity_registration_date DATE,
  termination_date DATE,
  termination_type VARCHAR,
  presumptive_income_regime VARCHAR,
  other_tax_regimes VARCHAR,
  source_snapshot_id VARCHAR
);

CREATE TABLE IF NOT EXISTS entity_activities (
  activity_record_id VARCHAR PRIMARY KEY,
  entity_id VARCHAR,
  activity_code VARCHAR,
  activity_name VARCHAR,
  activity_registration_date DATE,
  vat_affected VARCHAR,
  activity_category VARCHAR,
  activity_status VARCHAR,
  source_snapshot_id VARCHAR
);

CREATE TABLE IF NOT EXISTS entity_addresses (
  address_record_id VARCHAR PRIMARY KEY,
  entity_id VARCHAR,
  address_status VARCHAR,
  address_date DATE,
  address_type VARCHAR,
  street VARCHAR,
  street_number VARCHAR,
  block VARCHAR,
  apartment VARCHAR,
  village VARCHAR,
  city VARCHAR,
  commune VARCHAR,
  region VARCHAR,
  source_snapshot_id VARCHAR
);

CREATE TABLE IF NOT EXISTS ownership_edges (
  ownership_record_id VARCHAR PRIMARY KEY,
  entity_id VARCHAR,
  society_type VARCHAR,
  society_subtype VARCHAR,
  partner_rut VARCHAR,
  partner_entity_id VARCHAR,
  natural_person_group_source VARCHAR,
  partner_id_type VARCHAR,
  partner_group_id VARCHAR,
  ownership_percent DECIMAL(9,4),
  relationship_type VARCHAR,
  source_snapshot_id VARCHAR
);

CREATE TABLE IF NOT EXISTS evidence_links (
  evidence_id VARCHAR PRIMARY KEY,
  entity_id VARCHAR,
  source_id VARCHAR,
  source_url VARCHAR,
  source_snapshot_id VARCHAR,
  source_record_id VARCHAR,
  evidence_type VARCHAR,
  confidence VARCHAR,
  is_inference BOOLEAN DEFAULT FALSE
);
