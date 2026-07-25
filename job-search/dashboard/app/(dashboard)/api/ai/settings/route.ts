import { dashboardJsonResponse, dashboardMutationAuthErrorResponse } from '@/lib/server/auth'
import { isLocalModelName, saveLocalDraftingSettings } from '@/lib/local-drafting'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function POST(request: Request) {
  const authError = dashboardMutationAuthErrorResponse(request)
  if (authError) return authError
  try {
    const body = (await request.json()) as { enabled?: unknown; model?: unknown }
    if (typeof body.enabled !== 'boolean' || !isLocalModelName(body.model)) {
      return dashboardJsonResponse({ ok: false, error: 'Invalid local drafting settings.' }, { status: 400 })
    }
    return dashboardJsonResponse({ ok: true, data: await saveLocalDraftingSettings(body.enabled, body.model) })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Local drafting settings could not be saved.'
    return dashboardJsonResponse({ ok: false, error: message }, { status: error instanceof SyntaxError ? 400 : 409 })
  }
}
