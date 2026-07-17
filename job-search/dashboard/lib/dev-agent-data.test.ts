import { describe, expect, it } from 'vitest'

import {
  buildDashboardTask,
  isDevAgentAction,
  isDevAgentControlAction,
  isDevAgentProposalId,
  isDevAgentTaskId,
} from './dev-agent-data'

describe('development-agent dashboard task validation', () => {
  it('builds a bounded explorer task without accepting commands', () => {
    const task = buildDashboardTask({
      objective: 'Map the opportunity API and report the smallest safe test change.',
      role: 'explorer',
      allowedPaths: ['dashboard/app/api/opportunities', 'dashboard/lib'],
      verification: 'none',
      risk: 'low',
    })

    expect(task).toMatchObject({
      schema_version: 'career_local_dev_task_v1',
      role: 'explorer',
      allowed_paths: ['dashboard/app/api/opportunities', 'dashboard/lib'],
      acceptance_checks: [],
      timeout_seconds: 600,
    })
    expect(task).not.toHaveProperty('command')
  })

  it('maps dashboard verification to fixed shell-free checks', () => {
    const task = buildDashboardTask({
      objective: 'Add focused rendering tests for the development-agent run list.',
      role: 'implementer',
      allowedPaths: ['dashboard/app/dev-agents', 'dashboard/lib/dev-agent-data.test.ts'],
      verification: 'dashboard',
      risk: 'low',
    })

    expect(task.acceptance_checks).toEqual([
      expect.objectContaining({ argv: ['npm', 'test'], cwd: 'dashboard' }),
      expect.objectContaining({ argv: ['npm', 'run', 'typecheck'], cwd: 'dashboard' }),
    ])
    expect(task).toMatchObject({ max_changed_files: 8, max_diff_lines: 600, timeout_seconds: 1500 })
  })

  it('rejects broad or protected implementer paths', () => {
    const input = {
      objective: 'Change a bounded implementation detail and add its focused tests.',
      role: 'implementer',
      verification: 'python',
      risk: 'low',
    } as const

    expect(() => buildDashboardTask({ ...input, allowedPaths: ['.'] })).toThrow(/specific paths/i)
    expect(() => buildDashboardTask({ ...input, allowedPaths: ['pyproject.toml'] })).toThrow(/Main Codex/i)
    expect(() => buildDashboardTask({ ...input, allowedPaths: ['../outside'] })).toThrow(/safe and relative/i)
  })

  it('accepts only opaque ids and the three fixed dashboard actions', () => {
    expect(isDevAgentTaskId(`agent_${'a'.repeat(32)}`)).toBe(true)
    expect(isDevAgentTaskId('agent_123; rm file')).toBe(false)
    expect(isDevAgentAction('cancel')).toBe(true)
    expect(isDevAgentAction('reject')).toBe(true)
    expect(isDevAgentAction('apply')).toBe(true)
    expect(isDevAgentAction('approve')).toBe(false)
    expect(isDevAgentAction('run shell')).toBe(false)
    expect(isDevAgentProposalId(`proposal_${'b'.repeat(32)}`)).toBe(true)
    expect(isDevAgentProposalId('proposal_../../private')).toBe(false)
    expect(isDevAgentControlAction('run_planner')).toBe(true)
    expect(isDevAgentControlAction('qualify_qwen36')).toBe(true)
    expect(isDevAgentControlAction('arbitrary_model')).toBe(false)
  })
})
