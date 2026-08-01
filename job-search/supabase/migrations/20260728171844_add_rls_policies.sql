-- Enable RLS on tables that currently have it disabled
ALTER TABLE IF EXISTS public.workflow_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.notification_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.automation_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.automation_workers ENABLE ROW LEVEL SECURITY;

-- Allow anon role to SELECT all data (read-only dashboard access)
-- These are safe because the anon key is a publishable client-side key

CREATE POLICY "anon_select_opportunities"
  ON public.opportunities FOR SELECT
  TO anon
  USING (true);

CREATE POLICY "anon_select_opportunity_aliases"
  ON public.opportunity_aliases FOR SELECT
  TO anon
  USING (true);

CREATE POLICY "anon_select_opportunity_actions"
  ON public.opportunity_actions FOR SELECT
  TO anon
  USING (true);

CREATE POLICY "anon_select_source_runs"
  ON public.source_runs FOR SELECT
  TO anon
  USING (true);

CREATE POLICY "anon_select_daily_runs"
  ON public.daily_runs FOR SELECT
  TO anon
  USING (true);

CREATE POLICY "anon_select_notifications"
  ON public.notifications FOR SELECT
  TO anon
  USING (true);

CREATE POLICY "anon_select_notification_settings"
  ON public.notification_settings FOR SELECT
  TO anon
  USING (true);

CREATE POLICY "anon_select_deliveries"
  ON public.deliveries FOR SELECT
  TO anon
  USING (true);

CREATE POLICY "anon_select_workflow_runs"
  ON public.workflow_runs FOR SELECT
  TO anon
  USING (true);

CREATE POLICY "anon_select_recruiter_profiles"
  ON public.recruiter_profiles FOR SELECT
  TO anon
  USING (true);

CREATE POLICY "anon_select_recruiter_decisions"
  ON public.recruiter_decisions FOR SELECT
  TO anon
  USING (true);

CREATE POLICY "anon_select_approval_expirations"
  ON public.approval_expirations FOR SELECT
  TO anon
  USING (true);

CREATE POLICY "anon_select_profile_evidence"
  ON public.profile_evidence FOR SELECT
  TO anon
  USING (true);

CREATE POLICY "anon_select_operator_actions"
  ON public.operator_actions FOR SELECT
  TO anon
  USING (true);

CREATE POLICY "anon_select_followup_tasks"
  ON public.followup_tasks FOR SELECT
  TO anon
  USING (true);

CREATE POLICY "anon_select_campaign_runs"
  ON public.campaign_runs FOR SELECT
  TO anon
  USING (true);

CREATE POLICY "anon_select_automation_runs"
  ON public.automation_runs FOR SELECT
  TO anon
  USING (true);

CREATE POLICY "anon_select_automation_settings"
  ON public.automation_settings FOR SELECT
  TO anon
  USING (true);

CREATE POLICY "anon_select_automation_workers"
  ON public.automation_workers FOR SELECT
  TO anon
  USING (true);

CREATE POLICY "anon_select_cv_variants"
  ON public.cv_variants FOR SELECT
  TO anon
  USING (true);

CREATE POLICY "anon_select_cv_versions"
  ON public.cv_versions FOR SELECT
  TO anon
  USING (true);

CREATE POLICY "anon_select_user_settings"
  ON public.user_settings FOR SELECT
  TO anon
  USING (true);

