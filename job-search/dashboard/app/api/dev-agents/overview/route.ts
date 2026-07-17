import { getDevAgentOverview } from '../../../../lib/dev-agent-data'
import { dashboardAuthErrorResponse, dashboardJsonResponse } from '../../../../lib/server/auth'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(request: Request) {
  const authError = dashboardAuthErrorResponse(request)
  if (authError) return authError

  try {
    return dashboardJsonResponse({ ok: true, data: await getDevAgentOverview() })
  } catch {
    return dashboardJsonResponse(
      { ok: false, error: 'Development-agent status is temporarily unavailable.' },
      { status: 500 },
    )
  }
}
