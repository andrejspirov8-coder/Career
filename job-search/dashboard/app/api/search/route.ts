import { dashboardAuthErrorResponse, dashboardJsonResponse } from '../../../lib/server/auth'
import { buildGlobalSearch } from '../../../lib/global-search'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(request: Request) {
  const authError = dashboardAuthErrorResponse(request)
  if (authError) return authError

  const query = new URL(request.url).searchParams.get('q')?.trim() || ''
  if (query.length < 2 || query.length > 80) {
    return dashboardJsonResponse(
      { ok: false, error: 'Search must contain between 2 and 80 characters.' },
      { status: 400 },
    )
  }
  try {
    return dashboardJsonResponse({ ok: true, data: await buildGlobalSearch(query) })
  } catch {
    return dashboardJsonResponse({ ok: false, error: 'Search is temporarily unavailable.' }, { status: 500 })
  }
}
