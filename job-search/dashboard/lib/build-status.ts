import type { DashboardBuildStatus, DashboardRuntimeStatus } from './workspace-control-types'

const buildToleranceMs = 1_500

export function isBuildUpdateAvailable(builtAt: string, latestSourceModifiedAt: string): boolean {
  const builtAtMs = Date.parse(builtAt)
  const sourceMs = Date.parse(latestSourceModifiedAt)
  return Number.isFinite(builtAtMs)
    && Number.isFinite(sourceMs)
    && sourceMs > builtAtMs + buildToleranceMs
}

export function getDashboardBuildStatus(runtime: DashboardRuntimeStatus): DashboardBuildStatus {
  const builtAt = process.env.CAREER_DASHBOARD_BUILT_AT || ''
  const updateAvailable = isBuildUpdateAvailable(builtAt, runtime.latest_source_modified_at)
  return {
    built_at: builtAt,
    latest_source_modified_at: runtime.latest_source_modified_at,
    update_available: updateAvailable,
    restart_supported: runtime.restart_supported,
    last_restart_error: runtime.last_restart_error,
    status: !builtAt || !runtime.latest_source_modified_at ? 'unknown' : updateAvailable ? 'update_available' : 'current',
  }
}
