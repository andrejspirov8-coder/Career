import { dashboardAuthErrorResponse, dashboardJsonResponse } from '@/lib/server/auth'
import { getNotificationOverview } from '@/lib/notification-data'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(request: Request) {
  const authError = dashboardAuthErrorResponse(request)
  if (authError) return authError

  try {
    const force = new URL(request.url).searchParams.get('force') === '1'
    return dashboardJsonResponse({ ok: true, data: await getNotificationOverview({ force }) })
  } catch {
    return dashboardJsonResponse(
      { ok: false, error: 'The private notification inbox is temporarily unavailable.' },
      { status: 500 },
    )
  }
}
