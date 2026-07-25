import {
  cancelAutomationRun,
  isAutomationKind,
  isAutomationRunId,
  isScheduleTime,
  retryAutomationRun,
  saveAutomationSchedule,
  startAutomationRun,
} from '@/lib/automation-data'
import { dashboardJsonResponse, dashboardMutationAuthErrorResponse } from '@/lib/server/auth'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

type AutomationActionBody = {
  action?: unknown
  kind?: unknown
  runId?: unknown
  enabled?: unknown
  scheduleTime?: unknown
  timezone?: unknown
}

export async function POST(request: Request) {
  const authError = dashboardMutationAuthErrorResponse(request)
  if (authError) return authError

  let body: AutomationActionBody
  try {
    body = (await request.json()) as AutomationActionBody
  } catch {
    return dashboardJsonResponse({ ok: false, error: 'Invalid automation request.' }, { status: 400 })
  }

  try {
    if (body.action === 'start') {
      if (!isAutomationKind(body.kind)) {
        return dashboardJsonResponse({ ok: false, error: 'Unsupported automation action.' }, { status: 400 })
      }
      return dashboardJsonResponse({ ok: true, data: await startAutomationRun(body.kind) }, { status: 202 })
    }

    if (body.action === 'cancel') {
      if (!isAutomationRunId(body.runId)) {
        return dashboardJsonResponse({ ok: false, error: 'Invalid automation run id.' }, { status: 400 })
      }
      return dashboardJsonResponse({ ok: true, data: await cancelAutomationRun(body.runId) })
    }

    if (body.action === 'retry') {
      if (!isAutomationRunId(body.runId)) {
        return dashboardJsonResponse({ ok: false, error: 'Invalid automation run id.' }, { status: 400 })
      }
      return dashboardJsonResponse({ ok: true, data: await retryAutomationRun(body.runId) }, { status: 202 })
    }

    if (body.action === 'save_schedule') {
      if (
        typeof body.enabled !== 'boolean' ||
        !isScheduleTime(body.scheduleTime) ||
        body.timezone !== 'Europe/Vilnius'
      ) {
        return dashboardJsonResponse({ ok: false, error: 'Invalid schedule settings.' }, { status: 400 })
      }
      const data = await saveAutomationSchedule({
        enabled: body.enabled,
        scheduleTime: body.scheduleTime,
        timezone: body.timezone,
      })
      return dashboardJsonResponse({ ok: true, data })
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Automation action failed.'
    return dashboardJsonResponse({ ok: false, error: message }, { status: 409 })
  }

  return dashboardJsonResponse({ ok: false, error: 'Unsupported automation request.' }, { status: 400 })
}
