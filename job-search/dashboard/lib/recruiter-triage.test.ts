import { describe, expect, it } from 'vitest'
import {
  buildRecruiterActionPayload,
  filterTriageRows,
  rowsForSavedView,
  savedViewOrder,
  type TriageFilters,
} from './recruiter-triage'
import type { RecruiterOverview, RecruiterQueueRow } from './recruiter-data'

const rows: RecruiterQueueRow[] = [
  {
    profile_url: 'https://www.linkedin.com/in/lina-area/',
    name: 'Lina Area',
    headline: 'Area Manager premium retail',
    persona: 'retail_area_leader',
    cv_variant: 'luxury-retail',
    rank_score: 88,
    risk_flags: [],
    note: 'Hi Lina',
    approval: { approved: true, reason: 'approved', note_hash: 'abc123' },
  },
  {
    profile_url: 'https://www.linkedin.com/in/jane-review/',
    name: 'Jane Review',
    headline: 'Recruiter operations',
    persona: 'recruiter_hr',
    cv_variant: 'operations-management',
    rank_score: 64,
    risk_flags: ['low_confidence'],
    note: 'Hi Jane',
    approval: { approved: false, reason: 'missing_matching_approval', note_hash: 'def456' },
  },
]

function filters(overrides: Partial<TriageFilters> = {}): TriageFilters {
  return {
    query: '',
    persona: 'all',
    variant: 'all',
    riskFlag: 'all',
    approval: 'all',
    ...overrides,
  }
}

describe('recruiter triage helpers', () => {
  it('puts follow-ups and ready contacts before archive views', () => {
    expect(savedViewOrder.slice(0, 3)).toEqual(['follow_up', 'ready_to_contact', 'needs_review'])
    expect(savedViewOrder.at(-1)).toBe('sent_archive')
  })

  it('builds safe dashboard action payloads', () => {
    expect(buildRecruiterActionPayload('mark_skipped', { profileUrl: rows[0].profile_url })).toEqual({
      action: 'mark_skipped',
      profileUrl: rows[0].profile_url,
    })
    expect(buildRecruiterActionPayload('bulk_mark_review', { profileUrls: [rows[0].profile_url, rows[1].profile_url] })).toEqual({
      action: 'bulk_mark_review',
      profileUrls: [rows[0].profile_url, rows[1].profile_url],
    })
    expect(buildRecruiterActionPayload('copy_note_recorded', { profileUrl: rows[0].profile_url, note: 'Hi Lina' })).toEqual({
      action: 'copy_note_recorded',
      profileUrl: rows[0].profile_url,
      note: 'Hi Lina',
    })
    expect(buildRecruiterActionPayload('mark_sent_manual', { profileUrl: rows[0].profile_url, note: 'Hi Lina' })).toEqual({
      action: 'mark_sent_manual',
      profileUrl: rows[0].profile_url,
      note: 'Hi Lina',
    })
  })

  it('filters by search, persona, CV, risk, and approval', () => {
    expect(filterTriageRows(rows, filters({ query: 'premium' })).map((row) => row.name)).toEqual(['Lina Area'])
    expect(filterTriageRows(rows, filters({ persona: 'recruiter_hr' })).map((row) => row.name)).toEqual(['Jane Review'])
    expect(filterTriageRows(rows, filters({ variant: 'luxury-retail' })).map((row) => row.name)).toEqual(['Lina Area'])
    expect(filterTriageRows(rows, filters({ riskFlag: 'low_confidence' })).map((row) => row.name)).toEqual(['Jane Review'])
    expect(filterTriageRows(rows, filters({ approval: 'approved' })).map((row) => row.name)).toEqual(['Lina Area'])
    expect(filterTriageRows(rows, filters({ approval: 'not_approved' })).map((row) => row.name)).toEqual(['Jane Review'])
  })

  it('uses server-provided saved views when present', () => {
    const overview = {
      queues: {
        auto_send: [],
        review: [],
        skipped: [],
        sent: [],
        saved_views: {
          needs_review: [rows[1]],
          auto_send_candidates: [rows[0]],
          approved: [rows[0]],
          skipped: [],
          sent: [],
          risk_flags: [rows[1]],
        },
      },
    } as unknown as RecruiterOverview

    expect(rowsForSavedView(overview, 'needs_review')).toEqual([rows[1]])
    expect(rowsForSavedView(overview, 'risk_flags')).toEqual([rows[1]])
  })

  it('derives follow-up and ready-to-contact queues from existing records', () => {
    const sent = { ...rows[1], profile_url: 'https://www.linkedin.com/in/sent/', status: 'pending' }
    const overview = {
      queues: {
        auto_send: [rows[0]],
        review: [rows[1]],
        skipped: [],
        sent: [sent],
        saved_views: {},
      },
    } as unknown as RecruiterOverview

    expect(rowsForSavedView(overview, 'follow_up')).toEqual([sent])
    expect(rowsForSavedView(overview, 'ready_to_contact')).toEqual([rows[0]])
    expect(rowsForSavedView(overview, 'sent_archive')).toEqual([sent])
  })
})
