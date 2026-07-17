import { dashboardAuthErrorResponse, dashboardJsonResponse } from '../../../../lib/server/auth'
import { getWorkspaceControlStatus } from '../../../../lib/workspace-control'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(request: Request) {
  const authError = dashboardAuthErrorResponse(request)
  if (authError) return authError
  try {
    return dashboardJsonResponse({ ok: true, data: await getWorkspaceControlStatus() })
  } catch {
    return dashboardJsonResponse(
      { ok: false, error: 'Local workspace controls are temporarily unavailable.' },
      { status: 503 },
    )
  }
}
