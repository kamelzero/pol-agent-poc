CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE TABLE IF NOT EXISTS tracks_ais(
  ts timestamptz NOT NULL,
  scenario_id text,
  entity_id text,
  lat double precision,
  lon double precision,
  speed double precision,
  course double precision,
  h3 text,
  attrs jsonb
);
SELECT create_hypertable('tracks_ais', 'ts', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS tracks_adsb(
  ts timestamptz NOT NULL,
  scenario_id text,
  entity_id text,
  lat double precision,
  lon double precision,
  speed double precision,
  course double precision,
  alt double precision,
  h3 text,
  attrs jsonb
);
SELECT create_hypertable('tracks_adsb', 'ts', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS tracks_ground(
  ts timestamptz NOT NULL,
  scenario_id text,
  entity_id text,
  lat double precision,
  lon double precision,
  speed double precision,
  course double precision,
  h3 text,
  attrs jsonb
);
SELECT create_hypertable('tracks_ground', 'ts', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS anomalies_domain(
  ts timestamptz NOT NULL,
  domain text,
  entity_id text,
  h3 text,
  type text,
  score double precision,
  evidence jsonb
);
SELECT create_hypertable('anomalies_domain', 'ts', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS anomalies_fused(
  ts timestamptz NOT NULL,
  cluster_id text,
  types text[],
  h3_center text,
  entities text[],
  confidence double precision,
  evidence_links text[]
);
SELECT create_hypertable('anomalies_fused', 'ts', if_not_exists => TRUE);
