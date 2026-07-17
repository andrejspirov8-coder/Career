import { describe, expect, it } from 'vitest'

import { getDashboardBuildStatus, isBuildUpdateAvailable } from './build-status'

describe('dashboard build status', () => {
  it('detects runtime files changed after the embedded build time', () => {
    expect(isBuildUpdateAvailable('2026-07-15T10:00:00.000Z', '2026-07-15T10:00:03.000Z')).toBe(true)
    expect(isBuildUpdateAvailable('2026-07-15T10:00:00.000Z', '2026-07-15T10:00:01.000Z')).toBe(false)
    expect(isBuildUpdateAvailable('', new Date().toISOString())).toBe(false)
  })

  it('keeps supervisor and failure details in the displayed status', () => {
    const result = getDashboardBuildStatus({
      latest_source_modified_at: '2026-07-15T10:00:00.000Z',
      restart_supported: true,
      last_restart_error: 'previous build failed',
    })
    expect(result.restart_supported).toBe(true)
    expect(result.last_restart_error).toBe('previous build failed')
  })
})
