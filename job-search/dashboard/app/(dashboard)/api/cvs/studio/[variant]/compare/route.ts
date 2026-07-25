import { compareCvWithOpportunity } from '@/lib/cv-studio'
import { getCvVariantDefinition } from '@/lib/cv-data'
import { dashboardAuthErrorResponse, dashboardJsonResponse } from '@/lib/server/auth'
import { isOpportunityId } from '@/lib/opportunity-shared'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(
  request: Request,
  { params }: { params: Promise<{ variant: string }> },
) {
  const authError = dashboardAuthErrorResponse(request)
  if (authError) return authError
  const { variant } = await params
  if (!await getCvVariantDefinition(variant)) {
    return dashboardJsonResponse({ ok: false, error: 'Unknown CV variant.' }, { status: 404 })
  }
  const opportunityId = new URL(request.url).searchParams.get('opportunity')
  if (!isOpportunityId(opportunityId)) {
    return dashboardJsonResponse({ ok: false, error: 'Choose a valid opportunity.' }, { status: 400 })
  }
  try {
    return dashboardJsonResponse({
      ok: true,
      data: await compareCvWithOpportunity(variant, opportunityId),
    })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'CV comparison failed.'
    return dashboardJsonResponse({ ok: false, error: message }, { status: 422 })
  }
}
