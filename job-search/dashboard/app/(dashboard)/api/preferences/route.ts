import { dashboardAuthErrorResponse, dashboardJsonResponse, dashboardMutationAuthErrorResponse } from '@/lib/server/auth'
import {
  applyPreferenceSuggestion,
  getSearchPreferences,
  saveSearchPreferences,
} from '@/lib/search-preferences'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(request: Request) {
  const authError = dashboardAuthErrorResponse(request)
  if (authError) return authError

  try {
    return dashboardJsonResponse({ ok: true, data: await getSearchPreferences() })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Search preferences are unavailable.'
    return dashboardJsonResponse({ ok: false, error: message }, { status: 500 })
  }
}

export async function POST(request: Request) {
  const authError = dashboardMutationAuthErrorResponse(request)
  if (authError) return authError

  try {
    const body = (await request.json()) as { action?: unknown; preferences?: unknown; suggestion?: unknown }
    if (body.action === 'save') {
      return dashboardJsonResponse({ ok: true, data: await saveSearchPreferences(body.preferences) })
    }
    if (body.action === 'apply_suggestion') {
      return dashboardJsonResponse({ ok: true, data: await applyPreferenceSuggestion(body.suggestion) })
    }
    return dashboardJsonResponse({ ok: false, error: 'Unsupported preference action.' }, { status: 400 })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Search preference update failed.'
    const status = error instanceof SyntaxError ? 400 : 422
    return dashboardJsonResponse({ ok: false, error: message }, { status })
  }
}
