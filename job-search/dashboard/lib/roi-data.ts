import type { WeeklyRoiSummary } from './roi-types'
import { runPythonHelper } from './server/python-bridge'

const timeoutMs = 15_000

export function getWeeklyRoi(): Promise<WeeklyRoiSummary> {
  return runPythonHelper<WeeklyRoiSummary>('opportunities', ['weekly-roi'], {
    timeoutMs,
    maxOutputBytes: 2 * 1024 * 1024,
    errorLabel: 'Weekly ROI',
  })
}
