import { describe, expect, it } from 'vitest'

import {
  isOpportunityId,
  normalizeOpportunityOverview,
  type OpportunityRow,
  type RawOpportunityOverview,
} from './opportunity-data'
import {
  opportunityOverviewFixture,
  readyRow,
  reviewRow,
} from '../e2e/fixtures/opportunity-overview'

describe('opportunity overview normalization', () => {
  it('accepts only bounded opaque opportunity ids', () => {
    expect(isOpportunityId('opp_e2e-ready_42')).toBe(true)
    expect(isOpportunityId('../state/opportunities.sqlite3')).toBe(false)
    expect(isOpportunityId('job_123')).toBe(false)
    expect(isOpportunityId(`opp_${'a'.repeat(129)}`)).toBe(false)
  })

  it('returns each summary once, removes descriptions, and cuts repeated payloads by at least 75%', () => {
    const rowsById = new Map<string, OpportunityRow>([
      [readyRow.opportunity_id, { ...readyRow, description: 'Detailed role text. '.repeat(200) }],
      [reviewRow.opportunity_id, { ...reviewRow, description: 'Detailed watchlist text. '.repeat(200) }],
    ])
    const savedViews = Object.fromEntries(
      Object.entries(opportunityOverviewFixture.queues.saved_views).map(([name, ids]) => [
        name,
        ids.map((id) => rowsById.get(id) as OpportunityRow),
      ]),
    ) as RawOpportunityOverview['queues']['saved_views']
    const raw: RawOpportunityOverview = {
      ...opportunityOverviewFixture,
      schema: 'opportunity_dashboard_overview_v1',
      queues: {
        all: [...rowsById.values()],
        saved_views: savedViews,
      },
    }

    const normalized = normalizeOpportunityOverview(raw)
    const serialized = JSON.stringify(normalized)

    expect(normalized.queues.all).toHaveLength(2)
    expect(normalized.queues.saved_views.apply_ready).toEqual([readyRow.opportunity_id])
    expect(serialized).not.toContain('description')
    expect(serialized.length).toBeLessThanOrEqual(JSON.stringify(raw).length * 0.25)
  })
})
