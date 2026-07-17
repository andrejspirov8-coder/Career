import { dashboardJsonResponse, dashboardMutationAuthErrorResponse } from '../../../../lib/server/auth'
import { generateLocalDraft, isLocalDraftType } from '../../../../lib/local-drafting'
import { isOpportunityId } from '../../../../lib/opportunity-shared'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function POST(request: Request) {
  const authError = dashboardMutationAuthErrorResponse(request)
  if (authError) return authError
  try {
    const body = (await request.json()) as { opportunityId?: unknown; draftType?: unknown; instructions?: unknown }
    if (
      !isOpportunityId(body.opportunityId) ||
      !isLocalDraftType(body.draftType) ||
      typeof body.instructions !== 'string' ||
      body.instructions.length > 1000
    ) {
      return dashboardJsonResponse({ ok: false, error: 'Invalid local drafting request.' }, { status: 400 })
    }
    const data = await generateLocalDraft({
      opportunityId: body.opportunityId,
      draftType: body.draftType,
      instructions: body.instructions,
    })
    return dashboardJsonResponse({ ok: true, data })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'The local draft could not be created.'
    return dashboardJsonResponse({ ok: false, error: message }, { status: error instanceof SyntaxError ? 400 : 409 })
  }
}
