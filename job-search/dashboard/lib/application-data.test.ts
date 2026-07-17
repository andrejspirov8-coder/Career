import { describe, expect, it } from 'vitest'

import { buildApplicationCalendar, validateApplicationEntry } from './application-data'
import type { ApplicationWorkspaceOverview } from './application-types'

const entry = {
  opportunity_id: 'opp_application_test',
  deadline_date: '2026-07-20',
  reminder_date: '2026-07-18',
  next_step: 'Follow up with hiring manager',
  contact_name: 'Alex',
  notes: 'Tailor operations examples; keep metrics truthful.',
  cover_letter_status: 'draft',
  cover_letter_draft: 'Dear Hiring Team,',
  follow_up_draft: 'Hello, I wanted to follow up.',
  updated_at: '',
}

describe('application workspace data', () => {
  it('validates bounded dates, notes, and cover-letter state', () => {
    expect(validateApplicationEntry(entry)).toEqual(entry)
    expect(() => validateApplicationEntry({ ...entry, deadline_date: '20/07/2026' })).toThrow(/valid date/i)
    expect(() => validateApplicationEntry({ ...entry, cover_letter_status: 'auto_generated' })).toThrow(/valid cover letter/i)
    expect(() => validateApplicationEntry({ ...entry, cover_letter_draft: 'x'.repeat(8001) })).toThrow(/8,000/i)
  })

  it('exports deadlines and reminders as an escaped calendar', () => {
    const overview = {
      schema: 'career_application_workspace_v1',
      generated_at: '2026-07-15T00:00:00Z',
      counts: { active: 1, shortlisted: 1, applied: 0, follow_up: 0, due_next_7_days: 1, reminders_due: 0 },
      rows: [{
        ...entry,
        title: 'Operations Manager',
        company: 'Example, UAB',
        location: 'Vilnius',
        status: 'apply_ready',
        stage: 'shortlisted',
        source_url: 'https://jobs.example/1',
        fit_score: 28,
        cv_variant: 'operations-management',
        has_pack: true,
        cv_files: null,
        pack_files: [],
      }],
    } satisfies ApplicationWorkspaceOverview

    const calendar = buildApplicationCalendar(overview)
    expect(calendar).toContain('DTSTART;VALUE=DATE:20260720')
    expect(calendar).toContain('Application deadline: Operations Manager')
    expect(calendar).toContain('Example\\, UAB')
    expect(calendar.match(/BEGIN:VEVENT/g)).toHaveLength(2)
  })
})
