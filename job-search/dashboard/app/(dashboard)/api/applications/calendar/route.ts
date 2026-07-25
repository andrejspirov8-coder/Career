import { buildApplicationCalendar, getApplicationWorkspaceOverview } from '@/lib/application-data'
import { applyDashboardPrivateHeaders, dashboardAuthErrorResponse } from '@/lib/server/auth'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(request: Request) {
  const authError = dashboardAuthErrorResponse(request)
  if (authError) return authError
  const calendar = buildApplicationCalendar(await getApplicationWorkspaceOverview())
  return applyDashboardPrivateHeaders(new Response(calendar, {
    headers: {
      'Content-Disposition': 'attachment; filename="career-application-dates.ics"',
      'Content-Type': 'text/calendar; charset=utf-8',
    },
  }))
}
