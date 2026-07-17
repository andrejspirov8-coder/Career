import { getDevAgentRun, isDevAgentTaskId } from '../../../../../lib/dev-agent-data'
import { dashboardAuthErrorResponse, dashboardJsonResponse } from '../../../../../lib/server/auth'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(request: Request, { params }: { params: Promise<{ taskId: string }> }) {
  const authError = dashboardAuthErrorResponse(request)
  if (authError) return authError

  const { taskId } = await params
  if (!isDevAgentTaskId(taskId)) {
    return dashboardJsonResponse({ ok: false, error: 'Invalid development-agent task id.' }, { status: 400 })
  }
  try {
    return dashboardJsonResponse({ ok: true, data: await getDevAgentRun(taskId) })
  } catch {
    return dashboardJsonResponse({ ok: false, error: 'Development-agent run was not found.' }, { status: 404 })
  }
}
