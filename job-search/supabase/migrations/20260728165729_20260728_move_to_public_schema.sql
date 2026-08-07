-- Move all career schema tables to public for PostgREST compatibility
DROP SCHEMA IF EXISTS career CASCADE;

-- 1. OPPORTUNITIES
CREATE TABLE IF NOT EXISTS public.opportunities (
  opportunity_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id),
  dedupe_key TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_url TEXT,
  title TEXT,
  company TEXT,
  location TEXT,
  status TEXT NOT NULL DEFAULT 'new',
  data_json JSONB NOT NULL DEFAULT '{}',
  evidence_json JSONB,
  match_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_opportunities_dedupe ON public.opportunities(dedupe_key);
CREATE INDEX IF NOT EXISTS idx_opportunities_status ON public.opportunities(status);
CREATE INDEX IF NOT EXISTS idx_opportunities_fts ON public.opportunities USING GIN (to_tsvector('english', coalesce(title, '') || ' ' || coalesce(company, '')));

-- 2. OPPORTUNITY ACTIONS
CREATE TABLE IF NOT EXISTS public.opportunity_actions (
  id BIGSERIAL PRIMARY KEY,
  opportunity_id UUID NOT NULL REFERENCES public.opportunities(opportunity_id) ON DELETE CASCADE,
  action_type TEXT NOT NULL,
  old_status TEXT,
  new_status TEXT,
  operator_source TEXT,
  metadata_json JSONB DEFAULT '{}',
  idempotency_key TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_opp_actions_opp ON public.opportunity_actions(opportunity_id);
CREATE INDEX IF NOT EXISTS idx_opp_actions_idempotency ON public.opportunity_actions(opportunity_id, idempotency_key) WHERE idempotency_key IS NOT NULL;

-- 3. SOURCE RUNS
CREATE TABLE IF NOT EXISTS public.source_runs (
  id BIGSERIAL PRIMARY KEY,
  run_id TEXT NOT NULL,
  source TEXT NOT NULL,
  status TEXT NOT NULL,
  snapshot_type TEXT NOT NULL,
  item_count INTEGER NOT NULL DEFAULT 0,
  duration_ms INTEGER NOT NULL DEFAULT 0,
  error TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_source_runs_run ON public.source_runs(run_id);

-- 4. DAILY RUNS
CREATE TABLE IF NOT EXISTS public.daily_runs (
  run_id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  partial BOOLEAN NOT NULL DEFAULT false,
  output_json JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 5. OPPORTUNITY ALIASES
CREATE TABLE IF NOT EXISTS public.opportunity_aliases (
  alias_key TEXT PRIMARY KEY,
  alias_type TEXT NOT NULL,
  opportunity_id UUID NOT NULL REFERENCES public.opportunities(opportunity_id) ON DELETE CASCADE,
  source TEXT NOT NULL,
  native_source_id TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_opp_aliases_opp ON public.opportunity_aliases(opportunity_id);

-- 6. DELIVERIES
CREATE TABLE IF NOT EXISTS public.deliveries (
  id BIGSERIAL PRIMARY KEY,
  delivery_date DATE NOT NULL,
  canonical_identity TEXT NOT NULL,
  opportunity_id UUID NOT NULL REFERENCES public.opportunities(opportunity_id) ON DELETE CASCADE,
  run_id TEXT NOT NULL,
  delivered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(delivery_date, canonical_identity)
);

-- 7. RECRUITER PROFILES
CREATE TABLE IF NOT EXISTS public.recruiter_profiles (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id),
  profile_url TEXT UNIQUE NOT NULL,
  name TEXT,
  title TEXT,
  company TEXT,
  location TEXT,
  source TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_recruiter_profiles_name ON public.recruiter_profiles USING GIN (name gin_trgm_ops);

-- 8. WORKFLOW RUNS
CREATE TABLE IF NOT EXISTS public.workflow_runs (
  run_id TEXT PRIMARY KEY,
  mode TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  dry_run BOOLEAN NOT NULL DEFAULT true,
  config_hash TEXT
);

-- 9. RECRUITER DECISIONS
CREATE TABLE IF NOT EXISTS public.recruiter_decisions (
  id BIGSERIAL PRIMARY KEY,
  profile_url TEXT NOT NULL REFERENCES public.recruiter_profiles(profile_url) ON DELETE CASCADE,
  run_id TEXT NOT NULL REFERENCES public.workflow_runs(run_id),
  score REAL,
  tier TEXT,
  status TEXT NOT NULL,
  reason TEXT,
  note TEXT,
  note_hash TEXT,
  approved_at TIMESTAMPTZ,
  sent_at TIMESTAMPTZ,
  metadata_json JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_recruiter_decisions_profile_status ON public.recruiter_decisions(profile_url, status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_recruiter_decisions_approval_unique ON public.recruiter_decisions(profile_url, note_hash, status) WHERE status = 'approved';

-- 10. APPROVAL EXPIRATIONS
CREATE TABLE IF NOT EXISTS public.approval_expirations (
  id BIGSERIAL PRIMARY KEY,
  profile_url TEXT NOT NULL REFERENCES public.recruiter_profiles(profile_url) ON DELETE CASCADE,
  note_hash TEXT NOT NULL,
  approved_by TEXT,
  approval_reason TEXT,
  approved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ,
  metadata_json JSONB DEFAULT '{}',
  UNIQUE(profile_url, note_hash)
);

-- 11. PROFILE EVIDENCE
CREATE TABLE IF NOT EXISTS public.profile_evidence (
  profile_url TEXT PRIMARY KEY REFERENCES public.recruiter_profiles(profile_url) ON DELETE CASCADE,
  source TEXT,
  company_facts_json JSONB,
  persona_evidence_json JSONB,
  cv_fit_evidence_json JSONB,
  geo_evidence_json JSONB,
  risk_flags_json JSONB DEFAULT '[]',
  confidence REAL,
  run_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 12. OPERATOR ACTIONS
CREATE TABLE IF NOT EXISTS public.operator_actions (
  id BIGSERIAL PRIMARY KEY,
  action_type TEXT NOT NULL,
  profile_url TEXT NOT NULL REFERENCES public.recruiter_profiles(profile_url) ON DELETE CASCADE,
  note_hash TEXT,
  note TEXT,
  operator_source TEXT,
  metadata_json JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_operator_actions_profile ON public.operator_actions(profile_url, created_at);

-- 13. FOLLOWUP TASKS
CREATE TABLE IF NOT EXISTS public.followup_tasks (
  id BIGSERIAL PRIMARY KEY,
  profile_url TEXT NOT NULL REFERENCES public.recruiter_profiles(profile_url) ON DELETE CASCADE,
  task_type TEXT NOT NULL,
  due_at TIMESTAMPTZ,
  status TEXT NOT NULL,
  metadata_json JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 14. CAMPAIGN RUNS
CREATE TABLE IF NOT EXISTS public.campaign_runs (
  run_id TEXT PRIMARY KEY,
  stage TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  metadata_json JSONB DEFAULT '{}'
);

-- 15. NOTIFICATIONS
CREATE TABLE IF NOT EXISTS public.notifications (
  notification_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  category TEXT NOT NULL,
  kind TEXT NOT NULL,
  priority TEXT NOT NULL,
  lifecycle TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  href TEXT NOT NULL DEFAULT '',
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  source_updated_at TIMESTAMPTZ,
  desktop_eligible BOOLEAN NOT NULL DEFAULT false,
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  read_at TIMESTAMPTZ,
  dismissed_at TIMESTAMPTZ,
  snoozed_until TIMESTAMPTZ,
  resolved_at TIMESTAMPTZ,
  desktop_delivered_at TIMESTAMPTZ
);

-- 16. NOTIFICATION SETTINGS
CREATE TABLE IF NOT EXISTS public.notification_settings (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  desktop_enabled BOOLEAN NOT NULL DEFAULT false,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 17. AUTOMATION RUNS
CREATE TABLE IF NOT EXISTS public.automation_runs (
  run_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  status TEXT NOT NULL,
  trigger_source TEXT NOT NULL,
  unique_key TEXT,
  parent_run_id TEXT,
  requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  scheduled_for TIMESTAMPTZ,
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  heartbeat_at TIMESTAMPTZ,
  attempt INTEGER NOT NULL DEFAULT 1,
  phase TEXT NOT NULL DEFAULT 'pending',
  progress INTEGER NOT NULL DEFAULT 0,
  result_json JSONB NOT NULL DEFAULT '{}',
  error TEXT NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_automation_runs_unique_key ON public.automation_runs(unique_key) WHERE unique_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_automation_runs_status ON public.automation_runs(status, requested_at);

-- 18. AUTOMATION SETTINGS
CREATE TABLE IF NOT EXISTS public.automation_settings (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  schedule_enabled BOOLEAN NOT NULL DEFAULT false,
  schedule_time TEXT NOT NULL DEFAULT '08:00',
  timezone TEXT NOT NULL DEFAULT 'Europe/Vilnius',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 19. AUTOMATION WORKERS
CREATE TABLE IF NOT EXISTS public.automation_workers (
  worker_id TEXT PRIMARY KEY,
  pid INTEGER NOT NULL,
  mode TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  stopped_at TIMESTAMPTZ
);

-- 20. CV VARIANTS
CREATE TABLE IF NOT EXISTS public.cv_variants (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug TEXT NOT NULL,
  name TEXT NOT NULL,
  language TEXT NOT NULL,
  focus TEXT,
  display_order INTEGER,
  source_markdown TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(slug)
);

-- 21. CV VERSIONS
CREATE TABLE IF NOT EXISTS public.cv_versions (
  id BIGSERIAL PRIMARY KEY,
  variant_id UUID NOT NULL REFERENCES public.cv_variants(id) ON DELETE CASCADE,
  version_id TEXT NOT NULL,
  content TEXT NOT NULL,
  content_hash TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 22. USER SETTINGS
CREATE TABLE IF NOT EXISTS public.user_settings (
  user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  search_preferences_json JSONB,
  drafting_preferences_json JSONB,
  notification_settings_json JSONB,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Helper views and functions
CREATE OR REPLACE VIEW public.opportunity_status_counts AS
SELECT status, COUNT(*) AS count FROM public.opportunities GROUP BY status;

CREATE OR REPLACE FUNCTION public.count_opportunities_by_status()
RETURNS TABLE(status TEXT, count BIGINT) LANGUAGE SQL STABLE
AS $$ SELECT opp.status, COUNT(*)::BIGINT FROM public.opportunities opp GROUP BY opp.status; $$;

CREATE OR REPLACE FUNCTION public.count_recruiter_decisions_by_status()
RETURNS TABLE(status TEXT, count BIGINT) LANGUAGE SQL STABLE
AS $$ SELECT rd.status, COUNT(*)::BIGINT FROM public.recruiter_decisions rd GROUP BY rd.status; $$;

-- RLS on all tables
ALTER TABLE public.opportunities ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.opportunity_actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.source_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.daily_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.opportunity_aliases ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.deliveries ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.recruiter_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.recruiter_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.approval_expirations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.profile_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.operator_actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.followup_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.campaign_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.automation_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cv_variants ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cv_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_settings ENABLE ROW LEVEL SECURITY;
