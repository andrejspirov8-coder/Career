import { dashboardAuthErrorResponse, dashboardJsonResponse } from '../../../../lib/server/auth'
import { getOpportunityDetail, isOpportunityId } from '../../../../lib/opportunity-data'

export const dynamic = 'force-dynamic'

export async function GET(
  request: Request,
  { params }: { params: Promise<{ opportunityId: string }> },
) {
  const authError = dashboardAuthErrorResponse(request)
  if (authError) return authError

  try {
    const { opportunityId } = await params
    if (!isOpportunityId(opportunityId)) {
      return dashboardJsonResponse({ ok: false, error: 'A valid opportunityId is required.' }, { status: 400 })
    }
    return dashboardJsonResponse({ ok: true, data: await getOpportunityDetail(opportunityId) })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Opportunity detail failed.'
    const status = message.includes('not found') ? 404 : 500
    return dashboardJsonResponse({ ok: false, error: message }, { status })
  }
}
