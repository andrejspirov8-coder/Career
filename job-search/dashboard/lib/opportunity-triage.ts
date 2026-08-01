import type { OpportunityActionName, OpportunityOverview, OpportunitySummary } from './opportunity-data'

export type OpportunityViewKey =
  | 'daily_queue'
  | 'stage_new'
  | 'stage_review'
  | 'stage_shortlisted'
  | 'stage_pack_ready'
  | 'stage_applied'
  | 'stage_follow_up'
  | 'stage_closed'
  | 'fresh_live_matches'
  | 'new_today'
  | 'updated_roles'
  | 'closing_soon'
  | 'top_5_today'
  | 'apply_today'
  | 'needs_live_verification'
  | 'best_europe_matches'
  | 'best_matches'
  | 'needs_review'
  | 'apply_ready'
  | 'needs_cv_tailoring'
  | 'company_watchlist'
  | 'recruiter_contact'
  | 'applied'
  | 'missing_outcome'
  | 'follow_up'
  | 'skipped'
  | 'expired'
  | 'likely_duplicate'
  | 'likely_expired'
  | 'risk_flags'
  | 'blockers'
  | 'warnings'

export const opportunityViewOrder: OpportunityViewKey[] = [
  'daily_queue',
  'stage_new',
  'stage_review',
  'stage_shortlisted',
  'stage_pack_ready',
  'stage_applied',
  'stage_follow_up',
  'stage_closed',
  'fresh_live_matches',
  'needs_live_verification',
  'closing_soon',
  'missing_outcome',
  'blockers',
  'warnings',
]

const defaultOpportunityViewOrder: OpportunityViewKey[] = [
  'daily_queue',
  'top_5_today',
  'stage_shortlisted',
  'stage_pack_ready',
  'stage_follow_up',
  'stage_applied',
  'stage_new',
  'needs_live_verification',
  'stage_review',
  'stage_closed',
]

export const opportunityViewLabels: Record<OpportunityViewKey, string> = {
  daily_queue: 'Daily Queue',
  stage_new: 'New',
  stage_review: 'Review',
  stage_shortlisted: 'Shortlisted',
  stage_pack_ready: 'Pack Ready',
  stage_applied: 'Applied',
  stage_follow_up: 'Follow-up',
  stage_closed: 'Closed',
  fresh_live_matches: 'Fresh Live Matches',
  new_today: 'New Today',
  updated_roles: 'Updated Roles',
  closing_soon: 'Closing Soon',
  top_5_today: 'Top 5 Today',
  apply_today: 'Apply Today',
  needs_live_verification: 'Needs Live Verification',
  best_europe_matches: 'Best Europe Matches',
  best_matches: 'Best Matches',
  needs_review: 'Needs Review',
  apply_ready: 'Apply Ready',
  needs_cv_tailoring: 'Needs CV Tailoring',
  company_watchlist: 'Company Watchlist',
  recruiter_contact: 'Recruiter Contact',
  applied: 'Applied',
  missing_outcome: 'Missing Outcome',
  follow_up: 'Follow Up',
  skipped: 'Skipped',
  expired: 'Expired',
  likely_duplicate: 'Likely Duplicate',
  likely_expired: 'Likely Expired',
  risk_flags: 'Risk Flags',
  blockers: 'Blocked',
  warnings: 'Warnings',
}

export type OpportunityFilters = {
  query: string
  sourceKind: string
  variant: string
  status: string
  risk: 'all' | 'flagged' | 'clean'
}

export type OpportunityActionPayload = {
  action: OpportunityActionName
  opportunityId?: string
  requestId?: string
  applicationUrl?: string
  applicationNotes?: string
  applicationOutcome?: string
  decisionReason?: string
  decisionNote?: string
}

export function rowsForOpportunityView(overview: OpportunityOverview, view: OpportunityViewKey): OpportunitySummary[] {
  const rowsById = new Map(overview.queues.all.map((row) => [row.opportunity_id, row]))
  return (overview.queues.saved_views[view] || [])
    .map((opportunityId) => rowsById.get(opportunityId))
    .filter((row): row is OpportunitySummary => Boolean(row))
}

export function firstNonEmptyOpportunityView(overview: OpportunityOverview): OpportunityViewKey {
  return defaultOpportunityViewOrder.find((view) => rowsForOpportunityView(overview, view).length) ?? 'stage_review'
}

export function filterOpportunityRows(rows: OpportunitySummary[], filters: OpportunityFilters): OpportunitySummary[] {
  const needle = filters.query.trim().toLowerCase()
  return rows.filter((row) => {
    const haystack = [
      row.title,
      row.company,
      row.location,
      row.source,
      row.source_kind,
      row.source_url,
      row.live_status,
      row.live_check_note,
      row.match?.best_variant,
      row.match?.role_track,
      row.evidence.risk_flags.join(' '),
    ].filter(Boolean).join(' ').toLowerCase()
    if (needle && !haystack.includes(needle)) return false
    if (filters.sourceKind !== 'all' && row.source_kind !== filters.sourceKind) return false
    if (filters.variant !== 'all' && row.match?.best_variant !== filters.variant) return false
    if (filters.status !== 'all' && row.status !== filters.status) return false
    const attentionFlags = [
      ...(row.evidence.blockers || []),
      ...(row.evidence.warnings || []),
    ]
    if (filters.risk === 'flagged' && !attentionFlags.length) return false
    if (filters.risk === 'clean' && attentionFlags.length) return false
    return true
  })
}

type OpportunitySelectionRow = Pick<OpportunitySummary, 'opportunity_id'>

export function nextOpportunitySelection(
  beforeRows: readonly OpportunitySelectionRow[],
  afterRows: readonly OpportunitySelectionRow[],
  selectedId: string | null,
): string | null {
  if (!afterRows.length) return null
  if (selectedId && afterRows.some((row) => row.opportunity_id === selectedId)) return selectedId

  const previousIndex = selectedId
    ? beforeRows.findIndex((row) => row.opportunity_id === selectedId)
    : 0
  const nextIndex = Math.min(Math.max(previousIndex, 0), afterRows.length - 1)
  return afterRows[nextIndex]?.opportunity_id || null
}

export function moveOpportunitySelection(
  rows: readonly OpportunitySelectionRow[],
  selectedId: string | null,
  direction: -1 | 1,
): string | null {
  if (!rows.length) return null
  const currentIndex = selectedId
    ? rows.findIndex((row) => row.opportunity_id === selectedId)
    : -1
  if (currentIndex < 0) return rows[0]?.opportunity_id || null
  const nextIndex = Math.min(Math.max(currentIndex + direction, 0), rows.length - 1)
  return rows[nextIndex]?.opportunity_id || null
}

export function buildOpportunityActionPayload(
  action: OpportunityActionName,
  options: {
    opportunityId?: string
    applicationUrl?: string
    applicationNotes?: string
    applicationOutcome?: string
    decisionReason?: string
    decisionNote?: string
  } = {},
): OpportunityActionPayload {
  const payload: OpportunityActionPayload = { action }
  if (options.opportunityId) payload.opportunityId = options.opportunityId
  if (options.applicationUrl) payload.applicationUrl = options.applicationUrl
  if (options.applicationNotes) payload.applicationNotes = options.applicationNotes
  if (options.applicationOutcome) payload.applicationOutcome = options.applicationOutcome
  if (options.decisionReason) payload.decisionReason = options.decisionReason
  if (options.decisionNote) payload.decisionNote = options.decisionNote
  return payload
}
