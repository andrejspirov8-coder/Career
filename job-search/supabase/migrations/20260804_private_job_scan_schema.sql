-- Career job-search: private-schema for the expanded job-scan automation
-- Migration: 20260804_private_job_scan_schema
-- Connects to remote Supabase project pmyerkymcueaxerpmesk
-- Creates private schema with settings, registry, report ledger,
-- and helper functions (fingerprint, normalize).

-- =====================================================================
-- 1. SCHEMA + SETTINGS
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS private;

-- job_search_settings: one-row tuning for freshness windows
CREATE TABLE IF NOT EXISTS private.job_search_settings (
  id              INTEGER PRIMARY KEY CHECK (id = 1),
  fresh_days      INTEGER NOT NULL DEFAULT 30,
  exceptional_days INTEGER NOT NULL DEFAULT 90,
  max_report_per_run INTEGER NOT NULL DEFAULT 50,
  -- Geography priorities (JSON array of priority levels)
  geography_priorities JSONB NOT NULL DEFAULT '["vtl","lt_remote","lt","baltics","eu_eea","pl_berlin"]'::jsonb,
  -- Role lanes (JSON array of lane labels)
  role_lanes      JSONB NOT NULL DEFAULT '[
    "retail_luxury",
    "operations",
    "it_business"
  ]'::jsonb,
  -- Salary band (gross monthly, EUR)
  salary_min_gross_eur REAL NOT NULL DEFAULT 2800,
  salary_max_gross_eur REAL NOT NULL DEFAULT 3800,
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO private.job_search_settings (id) VALUES (1)
  ON CONFLICT (id) DO NOTHING;

-- =====================================================================
-- 2. REGISTRY — tracks every job the automation has seen
-- =====================================================================

CREATE TABLE IF NOT EXISTS private.job_search_registry (
  job_id            TEXT PRIMARY KEY,            -- source:native_id or canonical URL hash
  fingerprint       TEXT NOT NULL,               -- private.job_fingerprint(company,title,location)
  title             TEXT NOT NULL,
  company           TEXT NOT NULL,
  location          TEXT,
  source            TEXT NOT NULL,               -- source name (e.g. "cvbank", "linkedin")
  source_job_id     TEXT,                        -- employer/recruiter native ID
  canonical_url     TEXT NOT NULL,               -- direct employer URL (marketplace URLs go to aliases)
  source_aliases    JSONB DEFAULT '[]'::jsonb,   -- marketplace URLs as aliases
  status            TEXT NOT NULL DEFAULT 'discovered',
  -- Statuses: discovered, reported_new, reported_updated, reported_relisted,
  --            suppressed_stale, suppressed_noise, suppressed_low_fit,
  --            suppressed_ineligible, applied, dismissed, rejected, closed, expired, skipped
  event_kind        TEXT,                        -- last reported kind (new/updated/relisted)
  first_seen_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_reported_at  TIMESTAMPTZ,
  publication_date  TIMESTAMPTZ,
  closing_date      TIMESTAMTZRANGE,
  salary_min_gross  REAL,
  salary_max_gross  REAL,
  salary_currency   TEXT DEFAULT 'EUR',
  work_model        TEXT,                        -- onsite, hybrid, remote
  cv_recommended    TEXT,                        -- which CV variant slug
  fit_score         REAL,                        -- 0-100 match score
  material_hash     TEXT,                        -- hash of material fields (salary, deadline, location, reqs)
  notes             TEXT,                        -- free-text audit notes
  UNIQUE (job_id, source, status)                -- same job from different source = different registry row
);

CREATE INDEX IF NOT EXISTS idx_job_reg_fingerprint ON private.job_search_registry(fingerprint);
CREATE INDEX IF NOT EXISTS idx_job_reg_status ON private.job_search_registry(status);
CREATE INDEX IF NOT EXISTS idx_job_reg_canonical ON private.job_search_registry(canonical_url);
CREATE INDEX IF NOT EXISTS idx_job_reg_last_seen ON private.job_search_registry(last_seen_at);

-- =====================================================================
-- 3. REPORT VERSIONS — audit ledger of what was actually reported
-- =====================================================================

CREATE TABLE IF NOT EXISTS private.job_report_versions (
  report_id         TEXT PRIMARY KEY,            -- run_id:job_id
  run_id            TEXT NOT NULL,
  job_id            TEXT NOT NULL REFERENCES private.job_search_registry(job_id),
  event_kind        TEXT NOT NULL CHECK (event_kind IN ('reported_new', 'reported_updated', 'reported_relisted', 'suppressed_stale', 'suppressed_noise', 'suppressed_low_fit', 'suppressed_ineligible')),
  title             TEXT NOT NULL,
  company           TEXT NOT NULL,
  location          TEXT,
  salary_min_gross  REAL,
  salary_max_gross  REAL,
  salary_currency   TEXT DEFAULT 'EUR',
  closing_date      TIMESTAMPTZRANGE,
  source            TEXT NOT NULL,
  source_job_id     TEXT,
  canonical_url     TEXT NOT NULL,
  publication_date  TIMESTAMPTZ,
  material_delta    TEXT,                        -- for UPDATED: what changed
  cv_recommended    TEXT,
  fit_score         REAL,
  priority          TEXT,                        -- "Apply now" | "Consider" | "Skip"
  snapshot_json     JSONB NOT NULL DEFAULT '{}', -- compact job snapshot
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_job_reports_run ON private.job_report_versions(run_id);
CREATE INDEX IF NOT EXISTS idx_job_reports_job ON private.job_report_versions(job_id);
CREATE INDEX IF NOT EXISTS idx_job_reports_kind ON private.job_report_versions(event_kind);

-- =====================================================================
-- 4. HELPER FUNCTIONS
-- =====================================================================

-- job_fingerprint: deterministic hash of company+title+location for dedup
CREATE OR REPLACE FUNCTION private.job_fingerprint(p_company TEXT, p_title TEXT, p_location TEXT)
RETURNS TEXT
LANGUAGE SQL STABLE
SECURITY DEFINER
SET search_path = public, private
AS $$
  SELECT encode(
    pg_md5(
      lower(trim(coalesce(p_company, ''))) || '|' ||
      lower(trim(coalesce(p_title, ''))) || '|' ||
      lower(trim(coalesce(p_location, '')))
    ),
    'hex'
  );
$$;

-- job_normalize: clean and normalise raw job text into structured fields
CREATE OR REPLACE FUNCTION private.job_normalize(p_raw TEXT)
RETURNS TABLE(
  title       TEXT,
  company     TEXT,
  location    TEXT,
  salary_min  REAL,
  salary_max  REAL,
  currency    TEXT,
  work_model  TEXT,
  closing_date TIMESTAMPTZ,
  url         TEXT
)
LANGUAGE plpgsql STABLE
SECURITY DEFINER
SET search_path = public, private
AS $$
BEGIN
  -- Attempt basic extraction — caller should override with real parsing.
  -- This is a safe placeholder; all text fields must be validated
  -- by the Python layer before use.
  RETURN QUERY
  SELECT
    NULL::TEXT, NULL::TEXT, NULL::TEXT,
    NULL::REAL, NULL::REAL, NULL::TEXT, NULL::TEXT, NULL::TIMESTAMPTZ, NULL::TEXT;
END;
$$;

-- =====================================================================
-- 5. DAILY RUNS + SOURCE RUNS (kept in public per existing convention)
-- =====================================================================

-- These already exist from the main schema migration. We ensure they
-- have the expected columns. If dropped during the dormant cleanup
-- (20260802_drop_dormant_phase3_schema.sql), recreate them:

CREATE TABLE IF NOT EXISTS public.daily_runs (
  run_id        TEXT PRIMARY KEY,
  status        TEXT NOT NULL DEFAULT 'running',
  partial       BOOLEAN NOT NULL DEFAULT false,
  output_json   JSONB NOT NULL DEFAULT '{}',
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.source_runs (
  id            BIGSERIAL PRIMARY KEY,
  run_id        TEXT NOT NULL,
  source        TEXT NOT NULL,
  status        TEXT NOT NULL,
  snapshot_type TEXT NOT NULL,
  item_count    INTEGER NOT NULL DEFAULT 0,
  duration_ms   INTEGER NOT NULL DEFAULT 0,
  error         TEXT NOT NULL DEFAULT '',
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_source_runs_run ON public.source_runs(run_id);

-- =====================================================================
-- 6. OPPORTUNITIES + ALIASES (kept in public per existing convention)
-- =====================================================================

-- These already exist. Ensure minimal schema is present:

CREATE TABLE IF NOT EXISTS public.opportunities (
  opportunity_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  dedupe_key     TEXT NOT NULL,
  source_kind    TEXT NOT NULL,
  source_url     TEXT,
  title          TEXT,
  company        TEXT,
  location       TEXT,
  status         TEXT NOT NULL DEFAULT 'new',
  data_json      JSONB NOT NULL DEFAULT '{}',
  evidence_json  JSONB,
  match_json     JSONB,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_opportunities_dedupe ON public.opportunities(dedupe_key);

CREATE TABLE IF NOT EXISTS public.opportunity_aliases (
  alias_key       TEXT PRIMARY KEY,
  alias_type      TEXT NOT NULL,
  opportunity_id  UUID NOT NULL REFERENCES public.opportunities(opportunity_id) ON DELETE CASCADE,
  source          TEXT NOT NULL,
  native_source_id TEXT NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =====================================================================
-- 7. NOTES
-- =====================================================================
-- The private schema objects are designed for the expanded job-scan
-- automation described in the user request (2026-08-04).
-- RLS is intentionally OFF on these tables — the automation layer
-- uses the service role key and controls access at the application level.
-- If RLS is needed later, add policies that restrict writes to the
-- service role or a dedicated API key.
-- =====================================================================
