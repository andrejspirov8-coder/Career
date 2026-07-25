import { dashboardAuthErrorResponse, dashboardJsonResponse } from '@/lib/server/auth'
import { getOpportunityOverview } from '@/lib/opportunity-data'

export const dynamic = 'force-dynamic'

export async function GET(request: Request) {
  const authError = dashboardAuthErrorResponse(request)
  if (authError) return authError

  return dashboardJsonResponse(await getOpportunityOverview())
}
