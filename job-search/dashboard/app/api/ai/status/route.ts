import { dashboardAuthErrorResponse, dashboardJsonResponse } from '../../../../lib/server/auth'
import { getLocalDraftingStatus } from '../../../../lib/local-drafting'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(request: Request) {
  const authError = dashboardAuthErrorResponse(request)
  if (authError) return authError
  try {
    return dashboardJsonResponse({ ok: true, data: await getLocalDraftingStatus() })
  } catch {
    return dashboardJsonResponse({ ok: false, error: 'Local drafting status is unavailable.' }, { status: 503 })
  }
}
