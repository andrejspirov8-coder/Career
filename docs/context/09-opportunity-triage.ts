import type { OpportunityActionName, OpportunityOverview, OpportunitySummary } from './opportunity-data'

export type OpportunityViewKey =
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

export const opportunityViewOrder: OpportunityViewKey[] = [
  'fresh_live_matches',
  'top_5_today',
  'new_today',
  'updated_roles',
  'closing_soon',
  'apply_today',
  'needs_live_verification',
  'best_europe_matches',
  'best_matches',
  'needs_review',
  'needs_cv_tailoring',
  'apply_ready',
  'company_watchlist',
  'recruiter_contact',
  'applied',
  'missing_outcome',
  'follow_up',
  'skipped',
  'expired',
  'likely_duplicate',
  'likely_expired',
  'risk_flags',
]

export const opportunityViewLabels: Record<OpportunityViewKey, string> = {
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
  applicationUrl?: string
}

export function rowsForOpportunityView(overview: OpportunityOverview, view: OpportunityViewKey): OpportunitySummary[] {
  const rowsById = new Map(overview.queues.all.map((row) => [row.opportunity_id, row]))
  return (overview.queues.saved_views[view] || [])
    .map((opportunityId) => rowsById.get(opportunityId))
    .filter((row): row is OpportunitySummary => Boolean(row))
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
    if (filters.risk === 'flagged' && !row.evidence.risk_flags.length) return false
    if (filters.risk === 'clean' && row.evidence.risk_flags.length) return false
    return true
  })
}

export function buildOpportunityActionPayload(
  action: OpportunityActionName,
  options: { opportunityId?: string; applicationUrl?: string } = {},
): OpportunityActionPayload {
  const payload: OpportunityActionPayload = { action }
  if (options.opportunityId) payload.opportunityId = options.opportunityId
  if (options.applicationUrl) payload.applicationUrl = options.applicationUrl
  return payload
}
