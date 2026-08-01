-- Drop the dormant Phase-3 multi-tenant schema from the remote Supabase
-- project. These objects were created by 20260728_career_schema but never
-- wired up: the runtime data layer is 100% local SQLite and Supabase is used
-- for Auth only. All tables are empty (verified 2026-08-02) and no kept
-- table references them, so dropping is lossless. Populated mirror tables
-- (opportunities, source_runs, daily_runs, opportunity_aliases, notifications,
-- notification_settings) and Auth are untouched.

-- 1. Dormant helper view/functions (lint: SECURITY DEFINER / mutable search_path).
DROP VIEW IF EXISTS public.opportunity_status_counts;
DROP FUNCTION IF EXISTS public.count_opportunities_by_status();
DROP FUNCTION IF EXISTS public.count_recruiter_decisions_by_status();

-- 2. Dormant tables (16, all 0 rows). Single statement so PostgreSQL resolves
-- the internal FK graph; owned sequences and RLS policies drop with them.
DROP TABLE IF EXISTS
  public.approval_expirations,
  public.automation_runs,
  public.automation_settings,
  public.automation_workers,
  public.campaign_runs,
  public.cv_variants,
  public.cv_versions,
  public.deliveries,
  public.followup_tasks,
  public.operator_actions,
  public.opportunity_actions,
  public.profile_evidence,
  public.recruiter_decisions,
  public.recruiter_profiles,
  public.user_settings,
  public.workflow_runs;

-- 3. Extensions installed only for the dormant schema (no kept table uses
-- vector/trgm types or opclasses; verified via pg_depend).
DROP EXTENSION IF EXISTS vector;
DROP EXTENSION IF EXISTS pg_trgm;
