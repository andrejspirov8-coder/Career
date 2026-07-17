import type { CareerAnalyticsOverview } from './analytics-types'
import { runPythonHelper } from './server/python-bridge'

const timeoutMs = 20_000

export function getCareerAnalytics(): Promise<CareerAnalyticsOverview> {
  return runPythonHelper<CareerAnalyticsOverview>('analytics', ['overview'], {
    timeoutMs,
    maxOutputBytes: 4 * 1024 * 1024,
    errorLabel: 'Career analytics',
  })
}
