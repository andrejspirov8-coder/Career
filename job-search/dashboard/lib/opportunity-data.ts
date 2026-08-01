import { runPythonHelper } from './server/python-bridge'

export { isOpportunityId } from './opportunity-shared'

export type OpportunityStatus = 'new' | 'matched' | 'review' | 'apply_ready' | 'applied' | 'skipped' | 'expired' | 'follow_up'
export type OpportunitySourceKind = 'manual_inbox' | 'company_site' | 'ats' | 'job_alert' | 'job_board' | 'web_search' | 'recruiter'
export type OpportunityActionName = 'mark_review' | 'mark_skipped' | 'mark_apply_ready' | 'generate_pack' | 'mark_applied' | 'log_application' | 'update_application_outcome' | 'snooze_followup' | 'undo_last_decision'

export type OpportunityPreferenceFit = {
  eligible: boolean
  score: number
  reasons: string[]
  flags: string[]
}

export type OpportunityEvidence = {
  source_facts: string[]
  company_facts: string[]
  role_facts: string[]
  location_facts: string[]
  cv_fit_evidence: string[]
  risk_flags: string[]
  blockers?: string[]
  warnings?: string[]
  info?: string[]
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

export type OpportunityApplicationHistory = {
  date_iso: string
  company: string
  title: string
  variant_slug: string
  source: string
  outcome: string
  deadline_date: string
  match_score: string
  match_confidence: string
  salary_range: string
  tailored_cv: string
  response_date: string
  opportunity_id: string
  pack_dir: string
  application_url: string
  notes: string
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
  application_history?: OpportunityApplicationHistory[]
  risk?: {
    blockers: string[]
    warnings: string[]
    info: string[]
  }
  stage?: OpportunityStage
  preference?: OpportunityPreferenceFit
}

export type OpportunityStage = 'new' | 'review' | 'shortlisted' | 'pack_ready' | 'applied' | 'follow_up' | 'closed'

type RawOpportunitySavedViews = {
  fresh_live_matches: OpportunityRow[]
  delivery_candidates?: OpportunityRow[]
  new_today: OpportunityRow[]
  updated_roles: OpportunityRow[]
  closing_soon: OpportunityRow[]
  top_5_today: OpportunityRow[]
  daily_queue?: OpportunityRow[]
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
  blockers?: OpportunityRow[]
  warnings?: OpportunityRow[]
  stage_new?: OpportunityRow[]
  stage_review?: OpportunityRow[]
  stage_shortlisted?: OpportunityRow[]
  stage_pack_ready?: OpportunityRow[]
  stage_applied?: OpportunityRow[]
  stage_follow_up?: OpportunityRow[]
  stage_closed?: OpportunityRow[]
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
  | 'eligibility_reason'
  | 'salary_text'
  | 'deadline'
  | 'first_seen_at'
  | 'source_updated_at'
  | 'live_status'
  | 'live_checked_at'
  | 'live_check_note'
  | 'likely_closed'
  | 'status'
  | 'next_action'
> & {
  stage: OpportunityStage
  has_pack: boolean
  evidence: Pick<OpportunityEvidence, 'risk_flags' | 'confidence'> & {
    blockers: string[]
    warnings: string[]
    info: string[]
  }
  match?: Pick<
    OpportunityMatch,
    'best_variant' | 'score' | 'fit_score' | 'cv_score' | 'role_track' | 'confidence'
  > | null
  preference: OpportunityPreferenceFit
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
    daily_queue: number
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
    blockers: number
    warnings: number
  }
  funnel: {
    discovered: number
    deduplicated: number
    location_fit: number
    role_fit: number
    shortlisted: number
    apply_ready: number
  }
  pipeline: Record<OpportunityStage, number>
  queues: {
    all: OpportunitySummary[]
    saved_views: OpportunitySavedViewIds
  }
  safe_actions: OpportunityActionName[]
  search_profile?: {
    daily_queue_size: number
    updated_at: string
  }
  helperError?: string
}

export type RawOpportunityOverview = Omit<OpportunityOverview, 'schema' | 'queues' | 'funnel' | 'pipeline' | 'counts'> & {
  schema: 'opportunity_dashboard_overview_v1'
  counts: Omit<OpportunityOverview['counts'], 'blockers' | 'warnings' | 'daily_queue'>
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
  application_updated?: boolean
  application_csv?: string
  application_url?: string
  outcome?: string
  response_date?: string
  can_undo?: boolean
  undone_action?: string
  restored_status?: string
  decision_reason?: string
  decision_note?: string
  preference_suggestion?: {
    kind: 'add_excluded_company' | 'add_excluded_keyword'
    value: string
    label: string
  }
  preference_updated?: boolean
  error?: string
}

export type OpportunityCaptureInput = {
  url: string
  text: string
  title: string
  company: string
  location: string
}

export type OpportunityCaptureResult = {
  ok: boolean
  opportunity_id: string
  title: string
  company: string
  status: OpportunityStatus
  live_status: string
  fetched_url: false
}

export type OpportunityExport = {
  schema: 'career_opportunity_export_v1'
  generated_at: string
  opportunities: OpportunityRow[]
  applications: OpportunityApplicationHistory[]
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
      daily_queue: 0,
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
      blockers: 0,
      warnings: 0,
    },
    funnel: {
      discovered: 0,
      deduplicated: 0,
      location_fit: 0,
      role_fit: 0,
      shortlisted: 0,
      apply_ready: 0,
    },
    pipeline: {
      new: 0,
      review: 0,
      shortlisted: 0,
      pack_ready: 0,
      applied: 0,
      follow_up: 0,
      closed: 0,
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
        daily_queue: [],
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
        blockers: [],
        warnings: [],
        stage_new: [],
        stage_review: [],
        stage_shortlisted: [],
        stage_pack_ready: [],
        stage_applied: [],
        stage_follow_up: [],
        stage_closed: [],
      },
    },
    search_profile: { daily_queue_size: 5, updated_at: '' },
    safe_actions: ['mark_review', 'mark_skipped', 'mark_apply_ready', 'generate_pack', 'mark_applied', 'log_application', 'update_application_outcome', 'snooze_followup', 'undo_last_decision'],
    helperError,
  }
}

async function runHelper(args: string[]) {
  return runPythonHelper<unknown>('opportunities', args, {
    timeoutMs: 30_000,
    errorLabel: 'Opportunity helper',
  })
}

async function runHelperWithInput(args: string[], input: string): Promise<unknown> {
  return runPythonHelper<unknown>('opportunities', args, {
    inputText: input,
    timeoutMs: 30_000,
    maxOutputBytes: 8 * 1024 * 1024,
    errorLabel: 'Opportunity capture',
  })
}

function summarizeOpportunity(row: OpportunityRow): OpportunitySummary {
  const blockers = row.risk?.blockers || row.evidence?.blockers || []
  const warnings = row.risk?.warnings || row.evidence?.warnings || []
  const info = row.risk?.info || row.evidence?.info || []
  return {
    opportunity_id: row.opportunity_id,
    source: row.source,
    source_url: row.source_url,
    source_kind: row.source_kind,
    title: row.title,
    company: row.company,
    location: row.location,
    location_eligibility: row.location_eligibility,
    eligibility_reason: row.eligibility_reason,
    salary_text: row.salary_text,
    deadline: row.deadline,
    first_seen_at: row.first_seen_at,
    source_updated_at: row.source_updated_at,
    live_status: row.live_status,
    live_checked_at: row.live_checked_at,
    live_check_note: row.live_check_note,
    likely_closed: row.likely_closed,
    status: row.status,
    stage: row.stage || stageForOpportunity(row),
    next_action: row.next_action,
    has_pack: Boolean(row.pack),
    preference: row.preference || {
      eligible: true,
      score: 0,
      reasons: ['Recommended from CV fit and current role evidence'],
      flags: [],
    },
    evidence: {
      risk_flags: row.evidence?.risk_flags || [],
      confidence: row.evidence?.confidence || 0,
      blockers,
      warnings,
      info,
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

function stageForOpportunity(row: OpportunityRow): OpportunityStage {
  if (row.status === 'skipped' || row.status === 'expired' || row.live_status === 'closed' || row.likely_closed) return 'closed'
  if (row.status === 'follow_up') return 'follow_up'
  if (row.status === 'applied') return 'applied'
  if (row.status === 'apply_ready') return row.pack ? 'pack_ready' : 'shortlisted'
  if (row.status === 'matched') return 'shortlisted'
  if (row.status === 'review') return 'review'
  return 'new'
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
    funnel: {
      discovered: raw.counts.total,
      deduplicated: raw.counts.total - raw.counts.likely_duplicate,
      location_fit: raw.counts.total,
      role_fit: raw.counts.total - raw.counts.risk_flags,
      shortlisted: raw.counts.best_matches,
      apply_ready: raw.counts.apply_ready,
    },
    pipeline: {
      new: raw.counts.new_today,
      review: raw.counts.needs_review,
      shortlisted: raw.counts.best_matches,
      pack_ready: 0,
      applied: raw.counts.applied,
      follow_up: raw.counts.follow_up,
      closed: raw.counts.skipped + raw.counts.likely_expired,
    },
    counts: {
      ...raw.counts,
      daily_queue: raw.counts.top_5_today,
      blockers: raw.counts.risk_flags,
      warnings: 0,
    },
    queues: {
      all: raw.queues.all.map(summarizeOpportunity),
      saved_views: savedViews,
    },
  }
}

export async function getOpportunityOverview(): Promise<OpportunityOverview> {
  try {
    const raw = (await runHelper(['overview'])) as RawOpportunityOverview | OpportunityOverview
    return raw.schema === 'opportunity_dashboard_overview_v2'
      ? raw
      : normalizeOpportunityOverview(raw)
  } catch (error) {
    const message = error instanceof Error ? error.message : 'unknown helper error'
    return emptyOverview(message)
  }
}

export async function getOpportunityDetail(opportunityId: string): Promise<OpportunityRow> {
  return (await runHelper(['detail', '--opportunity-id', opportunityId])) as OpportunityRow
}

export async function getOpportunityExport(): Promise<OpportunityExport> {
  return (await runHelper(['export'])) as OpportunityExport
}

export async function captureOpportunity(input: OpportunityCaptureInput): Promise<OpportunityCaptureResult> {
  return (await runHelperWithInput(['capture'], JSON.stringify(input))) as OpportunityCaptureResult
}

export async function runOpportunityAction(
  action: OpportunityActionName,
  opportunityId: string,
  options: {
    applicationUrl?: string
    applicationNotes?: string
    applicationOutcome?: string
    decisionReason?: string
    decisionNote?: string
    requestId?: string
  } = {},
): Promise<OpportunityActionResult> {
  const args = ['action', '--name', action, '--opportunity-id', opportunityId]
  if (options.applicationUrl) args.push('--application-url', options.applicationUrl)
  if (options.applicationNotes) args.push('--application-notes', options.applicationNotes)
  if (options.applicationOutcome) args.push('--application-outcome', options.applicationOutcome)
  if (options.decisionReason) args.push('--decision-reason', options.decisionReason)
  if (options.decisionNote) args.push('--decision-note', options.decisionNote)
  return (await runHelper(args)) as OpportunityActionResult
}
