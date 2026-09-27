-- UrbanPulse NYC — Tiger Data / TimescaleDB schema
-- Run in the Tiger Data SQL editor (or psql) if you prefer manual setup.
-- The Streamlit app also auto-creates this table via SQLAlchemy.

CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

CREATE TABLE IF NOT EXISTS hazard_reports (
    id              BIGSERIAL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    location        TEXT NOT NULL,
    latitude        DOUBLE PRECISION,
    longitude       DOUBLE PRECISION,
    hazard_type     TEXT NOT NULL,
    severity        TEXT NOT NULL,
    agency          TEXT NOT NULL,
    confidence      DOUBLE PRECISION NOT NULL,
    priority        TEXT NOT NULL,
    summary         TEXT NOT NULL,
    council_email_subject TEXT NOT NULL,
    council_email_body    TEXT NOT NULL,
    ticket_json     JSONB NOT NULL,
    source          TEXT NOT NULL DEFAULT 'live',
    email_status    TEXT,
    email_to        TEXT,
    email_method    TEXT,
    PRIMARY KEY (id, created_at)
);

-- Convert to hypertable for high-velocity event logging (Tiger Data)
SELECT create_hypertable(
    'hazard_reports',
    by_range('created_at'),
    if_not_exists => TRUE,
    migrate_data => TRUE
);

CREATE INDEX IF NOT EXISTS hazard_reports_severity_idx ON hazard_reports (severity, created_at DESC);
CREATE INDEX IF NOT EXISTS hazard_reports_agency_idx   ON hazard_reports (agency, created_at DESC);

-- Example planner query (hourly severity counts)
-- SELECT time_bucket('1 hour', created_at) AS bucket,
--        severity,
--        COUNT(*) AS n
-- FROM hazard_reports
-- WHERE created_at > NOW() - INTERVAL '48 hours'
-- GROUP BY 1, 2
-- ORDER BY 1;
