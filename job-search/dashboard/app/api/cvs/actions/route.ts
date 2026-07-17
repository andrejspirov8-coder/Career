import { startAutomationRun } from '../../../../lib/automation-data'
import { dashboardJsonResponse, dashboardMutationAuthErrorResponse } from '../../../../lib/server/auth'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function POST(request: Request) {
  const authError = dashboardMutationAuthErrorResponse(request)
  if (authError) return authError

  let body: { action?: unknown }
  try {
    body = (await request.json()) as { action?: unknown }
  } catch {
    return dashboardJsonResponse({ ok: false, error: 'Invalid CV request.' }, { status: 400 })
  }
  if (body.action !== 'rebuild_all') {
    return dashboardJsonResponse({ ok: false, error: 'Unsupported CV action.' }, { status: 400 })
  }
  try {
    return dashboardJsonResponse(
      { ok: true, data: await startAutomationRun('cv_build') },
      { status: 202 },
    )
  } catch (error) {
    const message = error instanceof Error ? error.message : 'CV build could not be started.'
    return dashboardJsonResponse({ ok: false, error: message }, { status: 409 })
  }
}
