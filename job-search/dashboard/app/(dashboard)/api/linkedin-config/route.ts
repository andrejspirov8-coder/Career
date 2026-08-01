import { dashboardAuthErrorResponse, dashboardJsonResponse, dashboardMutationAuthErrorResponse } from '@/lib/server/auth'
import { getLinkedInConfig, saveLinkedInConfig } from '@/lib/linkedin-config'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(request: Request) {
  const authError = dashboardAuthErrorResponse(request)
  if (authError) return authError

  try {
    return dashboardJsonResponse({ ok: true, data: await getLinkedInConfig() })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'LinkedIn config is unavailable.'
    return dashboardJsonResponse({ ok: false, error: message }, { status: 500 })
  }
}

export async function POST(request: Request) {
  const authError = dashboardMutationAuthErrorResponse(request)
  if (authError) return authError

  try {
    const body = (await request.json()) as { action?: unknown; config?: unknown }
    if (body.action === 'save') {
      return dashboardJsonResponse({ ok: true, data: await saveLinkedInConfig(body.config) })
    }
    return dashboardJsonResponse({ ok: false, error: 'Unsupported LinkedIn config action.' }, { status: 400 })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'LinkedIn config update failed.'
    const status = error instanceof SyntaxError ? 400 : 422
    return dashboardJsonResponse({ ok: false, error: message }, { status })
  }
}
