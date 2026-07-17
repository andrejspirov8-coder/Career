import { getRecruiterOverview } from '../../../../lib/recruiter-data'
import { dashboardAuthErrorResponse, dashboardJsonResponse } from '../../../../lib/server/auth'

export const dynamic = 'force-dynamic'

export async function GET(request: Request) {
  const authError = dashboardAuthErrorResponse(request)
  if (authError) return authError

  return dashboardJsonResponse(await getRecruiterOverview())
}
