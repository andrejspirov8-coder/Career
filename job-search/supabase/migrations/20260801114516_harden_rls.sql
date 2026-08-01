-- Harden RLS: remove blanket anonymous read access and scope
-- authenticated reads to the owning user.

-- The dashboard reads data through the authenticated FastAPI bridge; the
-- SQLite database remains the canonical store at runtime. The anonymous
-- SELECT policies expose all rows to anyone holding the publishable anon
-- key with no user scoping. Drop them and replace with owner-scoped
-- policies on tables that carry a user_id column. service_role bypasses
-- RLS and is unaffected.

-- 1. Drop blanket anon SELECT policies on every table.
DROP POLICY IF EXISTS anon_select_opportunities ON public.opportunities;
DROP POLICY IF EXISTS anon_select_opportunity_aliases ON public.opportunity_aliases;
DROP POLICY IF EXISTS anon_select_opportunity_actions ON public.opportunity_actions;
DROP POLICY IF EXISTS anon_select_source_runs ON public.source_runs;
DROP POLICY IF EXISTS anon_select_daily_runs ON public.daily_runs;
DROP POLICY IF EXISTS anon_select_deliveries ON public.deliveries;
DROP POLICY IF EXISTS anon_select_notifications ON public.notifications;
DROP POLICY IF EXISTS anon_select_notification_settings ON public.notification_settings;
DROP POLICY IF EXISTS anon_select_workflow_runs ON public.workflow_runs;
DROP POLICY IF EXISTS anon_select_recruiter_profiles ON public.recruiter_profiles;
DROP POLICY IF EXISTS anon_select_recruiter_decisions ON public.recruiter_decisions;
DROP POLICY IF EXISTS anon_select_approval_expirations ON public.approval_expirations;
DROP POLICY IF EXISTS anon_select_profile_evidence ON public.profile_evidence;
DROP POLICY IF EXISTS anon_select_operator_actions ON public.operator_actions;
DROP POLICY IF EXISTS anon_select_followup_tasks ON public.followup_tasks;
DROP POLICY IF EXISTS anon_select_campaign_runs ON public.campaign_runs;
DROP POLICY IF EXISTS anon_select_automation_runs ON public.automation_runs;
DROP POLICY IF EXISTS anon_select_automation_settings ON public.automation_settings;
DROP POLICY IF EXISTS anon_select_automation_workers ON public.automation_workers;
DROP POLICY IF EXISTS anon_select_cv_variants ON public.cv_variants;
DROP POLICY IF EXISTS anon_select_cv_versions ON public.cv_versions;
DROP POLICY IF EXISTS anon_select_user_settings ON public.user_settings;

-- 2. Owner-scoped SELECT for authenticated users on tables that carry user_id.
-- user_id is stored as text; auth.uid() is a uuid.
CREATE POLICY "authenticated_select_own_opportunities"
  ON public.opportunities FOR SELECT
  TO authenticated
  USING (user_id = auth.uid()::text);

CREATE POLICY "authenticated_select_own_recruiter_profiles"
  ON public.recruiter_profiles FOR SELECT
  TO authenticated
  USING (user_id = auth.uid()::text);

CREATE POLICY "authenticated_select_own_user_settings"
  ON public.user_settings FOR SELECT
  TO authenticated
  USING (user_id = auth.uid()::text);
