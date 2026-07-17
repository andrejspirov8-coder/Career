import { execFile } from 'node:child_process'
import { join } from 'node:path'
import { promisify } from 'node:util'

const execFileAsync = promisify(execFile)
const repoRoot = join(process.cwd(), '..')

export type OpportunityStatus = 'new' | 'matched' | 'review' | 'apply_ready' | 'applied' | 'skipped' | 'expired' | 'follow_up'
export type OpportunitySourceKind = 'manual_inbox' | 'company_site' | 'ats' | 'job_alert' | 'job_board' | 'web_search' | 'recruiter'
export type OpportunityActionName = 'mark_review' | 'mark_skipped' | 'mark_apply_ready' | 'generate_pack' | 'mark_applied' | 'log_application' | 'snooze_followup'

export type OpportunityEvidence = {
  source_facts: string[]
  company_facts: string[]
  role_facts: string[]
  location_facts: string[]
  cv_fit_evidence: string[]
  risk_flags: string[]
  confidence: number
}

export type OpportunityMatch = {
  best_variant: string
  score: number
  fit_score: number
  cv_score: number
  location_score: number
  role_track_score: number
  source_score: number
  salary_score: number
  deadline_score: number
  risk_penalty: number
  role_track: string
  runner_up_variant: string
  runner_up_score: number
  margin_over_second: number
  confidence: string
  keyword_hits: string[]
  missing_keywords: string[]
  explanation: Record<string, string>
}

export type OpportunityPack = {
  pack_id: string
  pack_dir: string
  files: Record<string, string>
  generated_at: string
}

export type OpportunityActionHistory = {
  action_type: string
  old_status: string
  new_status: string
  operator_source: string
  metadata: Record<string, unknown>
  created_at: string
}

export type OpportunityRow = {
  opportunity_id: string
  source: string
  source_url: string
  source_kind: OpportunitySourceKind
  native_source_id?: string
  canonical_identity?: string
  title: string
  company: string
  location: string
  location_eligibility?: string
  eligibility_reason?: string
  first_eligible_at?: string
  remote_policy: string
  description: string
  salary_text?: string
  deadline?: string
  discovered_at: string
  first_seen_at: string
  last_seen_at: string
  last_checked_at: string
  source_updated_at: string
  live_status: 'live' | 'closed' | 'unverified' | 'unknown'
  live_checked_at: string
  live_check_method: string
  live_check_note: string
  content_hash: string
  likely_closed: boolean
  duplicate_cluster_id: string
  status: OpportunityStatus
  dedupe_key: string
  evidence: OpportunityEvidence
  match?: OpportunityMatch | null
  next_action: string
  pack?: OpportunityPack | null
  action_history?: OpportunityActionHistory[]
}

type RawOpportunitySavedViews = {
  fresh_live_matches: OpportunityRow[]
  delivery_candidates?: OpportunityRow[]
  new_today: OpportunityRow[]
  updated_roles: OpportunityRow[]
  closing_soon: OpportunityRow[]
  top_5_today: OpportunityRow[]
  apply_today: OpportunityRow[]
  needs_live_verification: OpportunityRow[]
  best_europe_matches: OpportunityRow[]
  best_matches: OpportunityRow[]
  needs_review: OpportunityRow[]
  apply_ready: OpportunityRow[]
  needs_cv_tailoring: OpportunityRow[]
  company_watchlist: OpportunityRow[]
  recruiter_contact: OpportunityRow[]
  applied: OpportunityRow[]
  missing_outcome: OpportunityRow[]
  follow_up: OpportunityRow[]
  skipped: OpportunityRow[]
  expired: OpportunityRow[]
  likely_duplicate: OpportunityRow[]
  likely_expired: OpportunityRow[]
  risk_flags: OpportunityRow[]
}

export type OpportunitySummary = Pick<
  OpportunityRow,
  | 'opportunity_id'
  | 'source'
  | 'source_url'
  | 'source_kind'
  | 'title'
  | 'company'
  | 'location'
  | 'location_eligibility'
  | 'deadline'
  | 'first_seen_at'
  | 'live_status'
  | 'live_checked_at'
  | 'live_check_note'
  | 'likely_closed'
  | 'status'
  | 'next_action'
> & {
  evidence: Pick<OpportunityEvidence, 'risk_flags' | 'confidence'>
  match?: Pick<
    OpportunityMatch,
    'best_variant' | 'score' | 'fit_score' | 'cv_score' | 'role_track' | 'confidence'
  > | null
}

export type OpportunitySavedViewIds = {
  [View in keyof RawOpportunitySavedViews]: string[]
}

export type OpportunityOverview = {
  schema: 'opportunity_dashboard_overview_v2'
  generated_at: string
  counts: {
    total: number
    fresh_live_matches: number
    new_today: number
    updated_roles: number
    closing_soon: number
    top_5_today: number
    apply_today: number
    needs_live_verification: number
    best_europe_matches: number
    best_matches: number
    needs_review: number
    apply_ready: number
    applied: number
    missing_outcome: number
    follow_up: number
    skipped: number
    likely_duplicate: number
    likely_expired: number
    risk_flags: number
  }
  queues: {
    all: OpportunitySummary[]
    saved_views: OpportunitySavedViewIds
  }
  safe_actions: OpportunityActionName[]
  helperError?: string
}

export type RawOpportunityOverview = Omit<OpportunityOverview, 'schema' | 'queues'> & {
  schema: 'opportunity_dashboard_overview_v1'
  queues: {
    all: OpportunityRow[]
    saved_views: RawOpportunitySavedViews
  }
}

export type OpportunityActionResult = {
  ok?: boolean
  opportunity_id?: string
  action_type?: string
  generated?: boolean
  pack_id?: string
  pack_dir?: string
  files?: Record<string, string>
  application_logged?: boolean
  application_csv?: string
  application_url?: string
  error?: string
}

function emptyOverview(helperError?: string): OpportunityOverview {
  return {
    schema: 'opportunity_dashboard_overview_v2',
    generated_at: new Date().toISOString(),
    counts: {
      total: 0,
      fresh_live_matches: 0,
      new_today: 0,
      updated_roles: 0,
      closing_soon: 0,
      top_5_today: 0,
      apply_today: 0,
      needs_live_verification: 0,
      best_europe_matches: 0,
      best_matches: 0,
      needs_review: 0,
      apply_ready: 0,
      applied: 0,
      missing_outcome: 0,
      follow_up: 0,
      skipped: 0,
      likely_duplicate: 0,
      likely_expired: 0,
      risk_flags: 0,
    },
    queues: {
      all: [],
      saved_views: {
        fresh_live_matches: [],
        delivery_candidates: [],
        new_today: [],
        updated_roles: [],
        closing_soon: [],
        top_5_today: [],
        apply_today: [],
        needs_live_verification: [],
        best_europe_matches: [],
        best_matches: [],
        needs_review: [],
        apply_ready: [],
        needs_cv_tailoring: [],
        company_watchlist: [],
        recruiter_contact: [],
        applied: [],
        missing_outcome: [],
        follow_up: [],
        skipped: [],
        expired: [],
        likely_duplicate: [],
        likely_expired: [],
        risk_flags: [],
      },
    },
    safe_actions: ['mark_review', 'mark_skipped', 'mark_apply_ready', 'generate_pack', 'mark_applied', 'log_application', 'snooze_followup'],
    helperError,
  }
}

async function runHelper(args: string[]) {
  const { stdout, stderr } = await execFileAsync('uv', ['run', 'python', 'tools/opportunity_dashboard.py', ...args], {
    cwd: repoRoot,
    maxBuffer: 1024 * 1024 * 8,
  })
  const parsed = JSON.parse(stdout || '{}') as { ok?: boolean; data?: unknown; error?: string }
  if (!parsed.ok) {
    throw new Error(parsed.error || stderr || 'Opportunity helper failed')
  }
  return parsed.data
}

function summarizeOpportunity(row: OpportunityRow): OpportunitySummary {
  return {
    opportunity_id: row.opportunity_id,
    source: row.source,
    source_url: row.source_url,
    source_kind: row.source_kind,
    title: row.title,
    company: row.company,
    location: row.location,
    location_eligibility: row.location_eligibility,
    deadline: row.deadline,
    first_seen_at: row.first_seen_at,
    live_status: row.live_status,
    live_checked_at: row.live_checked_at,
    live_check_note: row.live_check_note,
    likely_closed: row.likely_closed,
    status: row.status,
    next_action: row.next_action,
    evidence: {
      risk_flags: row.evidence?.risk_flags || [],
      confidence: row.evidence?.confidence || 0,
    },
    match: row.match
      ? {
          best_variant: row.match.best_variant,
          score: row.match.score,
          fit_score: row.match.fit_score,
          cv_score: row.match.cv_score,
          role_track: row.match.role_track,
          confidence: row.match.confidence,
        }
      : null,
  }
}

export function normalizeOpportunityOverview(raw: RawOpportunityOverview): OpportunityOverview {
  const savedViews = Object.fromEntries(
    Object.entries(raw.queues.saved_views).map(([view, rows]) => [
      view,
      rows.map((row) => row.opportunity_id),
    ]),
  ) as OpportunitySavedViewIds

  return {
    ...raw,
    schema: 'opportunity_dashboard_overview_v2',
    queues: {
      all: raw.queues.all.map(summarizeOpportunity),
      saved_views: savedViews,
    },
  }
}

export async function getOpportunityOverview(): Promise<OpportunityOverview> {
  try {
    return normalizeOpportunityOverview((await runHelper(['overview'])) as RawOpportunityOverview)
  } catch (error) {
    const message = error instanceof Error ? error.message : 'unknown helper error'
    return emptyOverview(message)
  }
}

export async function getOpportunityDetail(opportunityId: string): Promise<OpportunityRow> {
  return (await runHelper(['detail', '--opportunity-id', opportunityId])) as OpportunityRow
}

export async function runOpportunityAction(
  action: OpportunityActionName,
  opportunityId: string,
  options: { applicationUrl?: string } = {},
): Promise<OpportunityActionResult> {
  const args = ['action', '--name', action, '--opportunity-id', opportunityId]
  if (options.applicationUrl) args.push('--application-url', options.applicationUrl)
  return (await runHelper(args)) as OpportunityActionResult
}
