import { describe, expect, it } from 'vitest'
import {
  buildOpportunityActionPayload,
  filterOpportunityRows,
  firstNonEmptyOpportunityView,
  moveOpportunitySelection,
  nextOpportunitySelection,
  opportunityViewOrder,
  rowsForOpportunityView,
} from './opportunity-triage'
import type { OpportunityOverview, OpportunitySummary } from './opportunity-data'

const readySummary: OpportunitySummary = {
  opportunity_id: 'opp_ready',
  source: 'company_site',
  source_kind: 'manual_inbox',
  source_url: 'https://example.com/jobs/ready',
  title: 'Retail Operations Manager',
  company: 'Example Retail',
  location: 'Vilnius',
  deadline: '',
  first_seen_at: '2026-05-26T10:00:00+00:00',
  live_status: 'live',
  live_checked_at: '2026-05-26T10:00:00+00:00',
  live_check_note: 'matching_role_with_apply_signal',
  likely_closed: false,
  status: 'apply_ready',
  stage: 'pack_ready',
  next_action: 'make_pack',
  has_pack: true,
  evidence: { risk_flags: [], confidence: 0.85, blockers: [], warnings: [], info: [] },
  match: {
    best_variant: 'luxury-retail',
    score: 42,
    fit_score: 52,
    cv_score: 42,
    role_track: 'retail_operations',
    confidence: 'clear_winner',
  },
  preference: { eligible: true, score: 6, reasons: ['Matches your target role: retail operations'], flags: [] },
}

const overview: OpportunityOverview = {
  schema: 'opportunity_dashboard_overview_v2',
  generated_at: '2026-05-26T10:00:00+00:00',
  counts: {
    total: 2,
    fresh_live_matches: 1,
    new_today: 1,
    updated_roles: 0,
    closing_soon: 0,
    top_5_today: 1,
    daily_queue: 1,
    apply_today: 1,
    needs_live_verification: 0,
    best_europe_matches: 1,
    best_matches: 1,
    needs_review: 1,
    apply_ready: 1,
    applied: 0,
    missing_outcome: 0,
    follow_up: 0,
    skipped: 0,
    likely_duplicate: 0,
    likely_expired: 0,
    risk_flags: 1,
    blockers: 0,
    warnings: 1,
  },
  funnel: {
    discovered: 2,
    deduplicated: 2,
    location_fit: 2,
    role_fit: 1,
    shortlisted: 0,
    apply_ready: 1,
  },
  pipeline: {
    new: 0,
    review: 1,
    shortlisted: 0,
    pack_ready: 1,
    applied: 0,
    follow_up: 0,
    closed: 0,
  },
  safe_actions: ['mark_review', 'mark_skipped', 'mark_apply_ready', 'generate_pack', 'mark_applied', 'log_application', 'update_application_outcome', 'snooze_followup', 'undo_last_decision'],
  queues: {
    all: [readySummary],
    saved_views: {
      fresh_live_matches: [],
      delivery_candidates: [],
      best_matches: ['opp_ready'],
      top_5_today: [],
      daily_queue: [],
      new_today: [],
      updated_roles: [],
      closing_soon: [],
      apply_today: [],
      needs_live_verification: [],
      best_europe_matches: [],
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
      stage_pack_ready: ['opp_ready'],
      stage_applied: [],
      stage_follow_up: [],
      stage_closed: [],
    },
  },
}

describe('opportunity triage helpers', () => {
  it('returns rows for saved views', () => {
    expect(rowsForOpportunityView(overview, 'best_matches')).toHaveLength(1)
  })

  it('includes the wider opportunity review views before legacy views', () => {
    expect(opportunityViewOrder.slice(0, 8)).toEqual([
      'daily_queue',
      'stage_new',
      'stage_review',
      'stage_shortlisted',
      'stage_pack_ready',
      'stage_applied',
      'stage_follow_up',
      'stage_closed',
    ])
  })

  it('falls back to the saved shortlist before the full review backlog', () => {
    const fallbackOverview: OpportunityOverview = {
      ...overview,
      queues: {
        ...overview.queues,
        saved_views: {
          ...overview.queues.saved_views,
          top_5_today: [],
          daily_queue: [],
          stage_pack_ready: [],
          stage_shortlisted: ['opp_ready'],
          stage_review: ['opp_ready'],
        },
      },
    }
    expect(firstNonEmptyOpportunityView(fallbackOverview)).toBe('stage_shortlisted')
  })

  it('filters by text, source, CV variant, status, and risk state', () => {
    const rows = rowsForOpportunityView(overview, 'best_matches')
    expect(filterOpportunityRows(rows, {
      query: 'retail',
      sourceKind: 'manual_inbox',
      variant: 'luxury-retail',
      status: 'apply_ready',
      risk: 'all',
    })).toHaveLength(1)
    expect(filterOpportunityRows(rows, {
      query: 'retail',
      sourceKind: 'manual_inbox',
      variant: 'operations-management',
      status: 'apply_ready',
      risk: 'all',
    })).toHaveLength(0)
  })

  it('keeps the selected role or advances to the next useful row after a decision', () => {
    const before = [
      { opportunity_id: 'opp_one' },
      { opportunity_id: 'opp_two' },
      { opportunity_id: 'opp_three' },
    ]
    expect(nextOpportunitySelection(before, before, 'opp_two')).toBe('opp_two')
    expect(nextOpportunitySelection(before, [before[0], before[2]], 'opp_two')).toBe('opp_three')
    expect(nextOpportunitySelection(before, [before[0], before[1]], 'opp_three')).toBe('opp_two')
    expect(nextOpportunitySelection(before, [], 'opp_two')).toBeNull()
  })

  it('moves through the visible role list with bounded keyboard navigation', () => {
    const rows = [
      { opportunity_id: 'opp_one' },
      { opportunity_id: 'opp_two' },
      { opportunity_id: 'opp_three' },
    ]
    expect(moveOpportunitySelection(rows, null, 1)).toBe('opp_one')
    expect(moveOpportunitySelection(rows, 'opp_one', -1)).toBe('opp_one')
    expect(moveOpportunitySelection(rows, 'opp_one', 1)).toBe('opp_two')
    expect(moveOpportunitySelection(rows, 'opp_three', 1)).toBe('opp_three')
  })

  it('builds safe action payloads and never creates auto apply payloads', () => {
    expect(buildOpportunityActionPayload('generate_pack', { opportunityId: 'opp_ready' })).toEqual({
      action: 'generate_pack',
      opportunityId: 'opp_ready',
    })
    expect(buildOpportunityActionPayload('mark_applied', { opportunityId: 'opp_ready' })).toEqual({
      action: 'mark_applied',
      opportunityId: 'opp_ready',
    })
    expect(buildOpportunityActionPayload('log_application', {
      opportunityId: 'opp_ready',
      applicationUrl: 'https://example.com/apply',
      applicationNotes: 'Tailored the summary.',
    })).toEqual({
      action: 'log_application',
      opportunityId: 'opp_ready',
      applicationUrl: 'https://example.com/apply',
      applicationNotes: 'Tailored the summary.',
    })
    expect(buildOpportunityActionPayload('update_application_outcome', {
      opportunityId: 'opp_ready',
      applicationOutcome: 'interview',
    })).toEqual({
      action: 'update_application_outcome',
      opportunityId: 'opp_ready',
      applicationOutcome: 'interview',
    })
    expect(buildOpportunityActionPayload('mark_skipped', {
      opportunityId: 'opp_ready',
      decisionReason: 'not_relevant',
      decisionNote: 'Too sales-focused.',
    })).toEqual({
      action: 'mark_skipped',
      opportunityId: 'opp_ready',
      decisionReason: 'not_relevant',
      decisionNote: 'Too sales-focused.',
    })
  })
})
