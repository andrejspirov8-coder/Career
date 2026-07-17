import type { RecruiterActionName, RecruiterOverview, RecruiterQueueRow } from './recruiter-data'

export type SavedViewKey =
  | 'follow_up'
  | 'ready_to_contact'
  | 'needs_review'
  | 'auto_send_candidates'
  | 'approved'
  | 'skipped'
  | 'sent'
  | 'sent_archive'
  | 'risk_flags'

export type TriageFilters = {
  query: string
  persona: string
  variant: string
  riskFlag: string
  approval: 'all' | 'approved' | 'not_approved'
}

export type RecruiterActionPayload = {
  action: RecruiterActionName
  profileUrl?: string
  profileUrls?: string[]
  note?: string
}

export const savedViewOrder: SavedViewKey[] = [
  'follow_up',
  'ready_to_contact',
  'needs_review',
  'risk_flags',
  'skipped',
  'sent_archive',
]

export const savedViewLabels: Record<SavedViewKey, string> = {
  follow_up: 'Follow Up',
  ready_to_contact: 'Ready To Contact',
  needs_review: 'Needs Review',
  auto_send_candidates: 'Top Candidates',
  approved: 'Approved',
  skipped: 'Skipped',
  sent: 'Sent',
  sent_archive: 'Sent Archive',
  risk_flags: 'Risk Flags',
}

export function rowsForSavedView(overview: RecruiterOverview, view: SavedViewKey): RecruiterQueueRow[] {
  const serverRows = overview.queues.saved_views?.[view]
  if (serverRows) return serverRows

  const allActionRows = [
    ...overview.queues.auto_send,
    ...overview.queues.review,
    ...overview.queues.skipped,
  ]
  const sentRows = overview.queues.sent
  if (view === 'follow_up') {
    return sentRows.filter((row) => ['sent', 'pending', 'accepted'].includes(row.status || ''))
  }
  if (view === 'ready_to_contact') {
    return allActionRows.filter((row) => row.approval?.approved && !['sent', 'pending', 'accepted', 'replied'].includes(row.status || ''))
  }
  if (view === 'sent_archive') return sentRows

  if (view === 'needs_review') return overview.queues.review
  if (view === 'auto_send_candidates') return overview.queues.auto_send
  if (view === 'skipped') return overview.queues.skipped
  if (view === 'sent') return overview.queues.sent

  const actionRows = allActionRows
  if (view === 'approved') return actionRows.filter((row) => row.approval?.approved)
  if (view === 'risk_flags') return actionRows.filter((row) => Boolean(row.risk_flags?.length))
  return []
}

export function filterTriageRows(rows: RecruiterQueueRow[], filters: TriageFilters): RecruiterQueueRow[] {
  const needle = filters.query.trim().toLowerCase()
  return rows.filter((row) => {
    const haystack = [
      row.name,
      row.headline,
      row.company,
      row.location,
      row.profile_url,
      row.note,
      row.note_reason,
      row.source_backend,
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
    if (needle && !haystack.includes(needle)) return false
    if (filters.persona !== 'all' && row.persona !== filters.persona) return false
    if (filters.variant !== 'all' && row.cv_variant !== filters.variant) return false
    if (filters.riskFlag !== 'all' && !(row.risk_flags || []).includes(filters.riskFlag)) return false
    if (filters.approval === 'approved' && !row.approval?.approved) return false
    if (filters.approval === 'not_approved' && row.approval?.approved) return false
    return true
  })
}

export function buildRecruiterActionPayload(
  action: RecruiterActionName,
  options: { profileUrl?: string; profileUrls?: string[]; note?: string } = {},
): RecruiterActionPayload {
  if (action === 'approve_note' || action === 'update_note') {
    return { action, profileUrl: options.profileUrl, note: options.note }
  }
  if (action === 'mark_skipped' || action === 'mark_review') {
    return { action, profileUrl: options.profileUrl }
  }
  if (action === 'bulk_mark_skipped' || action === 'bulk_mark_review') {
    return { action, profileUrls: options.profileUrls || [] }
  }
  if (
    action === 'copy_note_recorded'
    || action === 'mark_sent_manual'
    || action === 'mark_pending'
    || action === 'mark_replied'
    || action === 'mark_accepted'
    || action === 'mark_rejected'
    || action === 'snooze_followup'
  ) {
    return { action, profileUrl: options.profileUrl, note: options.note }
  }
  return { action }
}
