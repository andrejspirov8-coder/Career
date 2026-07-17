import { dashboardAuthErrorResponse, dashboardJsonResponse } from '../../../lib/server/auth'
import { getDashboardOverview } from '../../../lib/repo-data'

export const dynamic = 'force-dynamic'

export async function GET(request: Request) {
  const authError = dashboardAuthErrorResponse(request)
  if (authError) return authError

  const overview = await getDashboardOverview()
  return dashboardJsonResponse(overview)
}
