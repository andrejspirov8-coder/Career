import { describe, expect, it } from 'vitest'

import type { ApplicationWorkspaceOverview } from './application-types'
import type { AutomationOverview } from './automation-data'
import { createNotificationCandidates } from './notification-data'
import type { OpportunityOverview } from './opportunity-data'

const now = new Date('2026-07-15T09:00:00Z')

function automationOverview(): AutomationOverview {
  return {
    schema: 'career_automation_overview_v1',
    generated_at: now.toISOString(),
    settings: {
      schedule_enabled: true,
      schedule_time: '08:00',
      timezone: 'Europe/Vilnius',
      updated_at: now.toISOString(),
    },
    worker: { online: false, status: 'stopped' },
    counts: {
      queued: 0,
      running: 0,
      cancel_requested: 0,
      succeeded: 1,
      partial: 0,
      failed: 0,
      cancelled: 0,
    },
    active_runs: [],
    recent_runs: [{
      run_id: `run_${'a'.repeat(32)}`,
      kind: 'daily_search',
      status: 'succeeded',
      trigger_source: 'schedule_catch_up',
      requested_at: '2026-07-15T08:00:00Z',
      finished_at: '2026-07-15T08:05:00Z',
      attempt: 1,
      phase: 'succeeded',
      progress: 100,
      result: { shown_count: 3 },
      error: '',
    }],
    source_health: {
      overall_status: 'healthy',
      last_checked_at: '2026-07-15T08:05:00Z',
      age_hours: 0,
      message: 'All sources completed.',
      sources: [],
    },
    available_actions: ['daily_search', 'cv_build'],
    safety: {
      scheduled_linkedin_enabled: false,
      live_linkedin_dispatch_enabled: false,
      message: 'LinkedIn stays manual.',
    },
  }
}

function opportunityOverview(): OpportunityOverview {
  return {
    schema: 'opportunity_dashboard_overview_v2',
    generated_at: now.toISOString(),
    counts: {} as OpportunityOverview['counts'],
    funnel: {} as OpportunityOverview['funnel'],
    pipeline: {} as OpportunityOverview['pipeline'],
    queues: {
      all: [{
        opportunity_id: 'opp_notification_test',
        title: 'Operations Manager',
        company: 'Example',
        location: 'Vilnius',
        source: 'company_site',
        source_url: 'https://example.com/job',
        source_kind: 'company_site',
        location_eligibility: 'eligible',
        eligibility_reason: 'Vilnius',
        salary_text: '',
        deadline: '2026-07-16',
        first_seen_at: '2026-07-15T06:00:00Z',
        source_updated_at: '2026-07-15T06:00:00Z',
        live_status: 'live',
        live_checked_at: '2026-07-15T06:00:00Z',
        live_check_note: 'Current listing',
        likely_closed: false,
        status: 'matched',
        stage: 'shortlisted',
        next_action: 'Review',
        has_pack: false,
        evidence: { risk_flags: [], confidence: 0.9, blockers: [], warnings: [], info: [] },
        match: {
          best_variant: 'operations-management',
          score: 27,
          fit_score: 27,
          cv_score: 20,
          role_track: 'operations',
          confidence: 'clear_winner',
        },
        preference: { eligible: true, score: 1, reasons: [], flags: [] },
      }],
      saved_views: {
        daily_queue: ['opp_notification_test'],
        top_5_today: ['opp_notification_test'],
      } as OpportunityOverview['queues']['saved_views'],
    },
    safe_actions: [],
  }
}

function applicationOverview(): ApplicationWorkspaceOverview {
  return {
    schema: 'career_application_workspace_v1',
    generated_at: now.toISOString(),
    counts: {
      active: 1,
      shortlisted: 0,
      applied: 0,
      follow_up: 1,
      due_next_7_days: 1,
      reminders_due: 1,
    },
    rows: [{
      opportunity_id: 'opp_notification_test',
      title: 'Operations Manager',
      company: 'Example',
      location: 'Vilnius',
      status: 'follow_up',
      stage: 'follow_up',
      source_url: 'https://example.com/job',
      fit_score: 27,
      cv_variant: 'operations-management',
      has_pack: true,
      cv_files: null,
      pack_files: [],
      deadline_date: '2026-07-16',
      reminder_date: '2026-07-14',
      next_step: 'Follow up',
      contact_name: '',
      notes: '',
      cover_letter_status: 'ready',
      cover_letter_draft: '',
      follow_up_draft: '',
      updated_at: '2026-07-14T10:00:00Z',
    }],
  }
}

describe('notification candidate generation', () => {
  it('creates a clear event for a catch-up run without a false missed-run alert', () => {
    const candidates = createNotificationCandidates({ automation: automationOverview(), now })

    expect(candidates).toEqual(expect.arrayContaining([
      expect.objectContaining({
        kind: 'automation_completed',
        title: 'Morning search caught up after wake',
        priority: 'info',
        lifecycle: 'event',
      }),
    ]))
    expect(candidates.some((candidate) => candidate.kind === 'schedule_missed')).toBe(false)
  })

  it('creates strong-role, deadline, and overdue follow-up notifications', () => {
    const candidates = createNotificationCandidates({
      opportunities: opportunityOverview(),
      applications: applicationOverview(),
      now,
    })

    expect(candidates.map((candidate) => candidate.kind)).toEqual([
      'strong_role',
      'application_deadline',
      'follow_up_due',
    ])
    expect(candidates.find((candidate) => candidate.kind === 'application_deadline')).toMatchObject({
      priority: 'urgent',
      title: 'Application deadline is tomorrow',
    })
    expect(candidates.find((candidate) => candidate.kind === 'follow_up_due')).toMatchObject({
      priority: 'urgent',
      title: 'Application follow-up is overdue',
    })
    expect(candidates.every((candidate) => candidate.href.startsWith('/'))).toBe(true)
  })

  it('creates one missed schedule condition and stable opaque ids', () => {
    const automation = automationOverview()
    automation.recent_runs = []
    const first = createNotificationCandidates({ automation, now })
    const second = createNotificationCandidates({ automation, now })
    const missed = first.find((candidate) => candidate.kind === 'schedule_missed')

    expect(missed).toMatchObject({ priority: 'urgent', lifecycle: 'condition' })
    expect(missed?.notification_id).toMatch(/^notification_[a-f0-9]{32}$/)
    expect(second.find((candidate) => candidate.kind === 'schedule_missed')?.notification_id)
      .toBe(missed?.notification_id)
  })
})
