import { dashboardAuthErrorResponse, dashboardJsonResponse, dashboardMutationAuthErrorResponse } from '@/lib/server/auth'
import { getOpportunitySources, saveOpportunitySources } from '@/lib/opportunity-sources'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(request: Request) {
  const authError = dashboardAuthErrorResponse(request)
  if (authError) return authError

  try {
    return dashboardJsonResponse({ ok: true, data: await getOpportunitySources() })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Opportunity sources are unavailable.'
    return dashboardJsonResponse({ ok: false, error: message }, { status: 500 })
  }
}

export async function POST(request: Request) {
  const authError = dashboardMutationAuthErrorResponse(request)
  if (authError) return authError

  try {
    const body = (await request.json()) as { action?: unknown; sources?: unknown }
    if (body.action === 'save') {
      return dashboardJsonResponse({ ok: true, data: await saveOpportunitySources(body.sources) })
    }
    return dashboardJsonResponse({ ok: false, error: 'Unsupported opportunity sources action.' }, { status: 400 })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Opportunity sources update failed.'
    const status = error instanceof SyntaxError ? 400 : 422
    return dashboardJsonResponse({ ok: false, error: message }, { status })
  }
}
