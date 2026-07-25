import { getAutomationRun, isAutomationRunId } from '@/lib/automation-data'
import { dashboardAuthErrorResponse, dashboardJsonResponse } from '@/lib/server/auth'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(request: Request, { params }: { params: Promise<{ runId: string }> }) {
  const authError = dashboardAuthErrorResponse(request)
  if (authError) return authError

  const { runId } = await params
  if (!isAutomationRunId(runId)) {
    return dashboardJsonResponse({ ok: false, error: 'Invalid automation run id.' }, { status: 400 })
  }
  try {
    return dashboardJsonResponse({ ok: true, data: await getAutomationRun(runId) })
  } catch {
    return dashboardJsonResponse({ ok: false, error: 'Automation run was not found.' }, { status: 404 })
  }
}
