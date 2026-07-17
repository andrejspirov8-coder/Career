import { describe, expect, it } from 'vitest'

import { isAutomationKind, isAutomationRunId, isScheduleTime } from './automation-data'

describe('automation dashboard input validation', () => {
  it('allows only the two fixed background actions', () => {
    expect(isAutomationKind('daily_search')).toBe(true)
    expect(isAutomationKind('cv_build')).toBe(true)
    expect(isAutomationKind('linkedin_dispatch')).toBe(false)
    expect(isAutomationKind('rm -rf')).toBe(false)
  })

  it('accepts opaque run ids and rejects paths or shell fragments', () => {
    expect(isAutomationRunId(`run_${'a'.repeat(32)}`)).toBe(true)
    expect(isAutomationRunId('../../state/automation.sqlite3')).toBe(false)
    expect(isAutomationRunId('run_123; echo unsafe')).toBe(false)
  })

  it('requires a valid 24-hour schedule time', () => {
    expect(isScheduleTime('08:30')).toBe(true)
    expect(isScheduleTime('23:59')).toBe(true)
    expect(isScheduleTime('8:30')).toBe(false)
    expect(isScheduleTime('24:00')).toBe(false)
  })
})
