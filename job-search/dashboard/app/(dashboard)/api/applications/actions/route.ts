import { saveApplicationEntry } from '@/lib/application-data'
import { dashboardJsonResponse, dashboardMutationAuthErrorResponse } from '@/lib/server/auth'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function POST(request: Request) {
  const authError = dashboardMutationAuthErrorResponse(request)
  if (authError) return authError
  try {
    const body = (await request.json()) as { action?: unknown; entry?: unknown }
    if (body.action !== 'save_entry') {
      return dashboardJsonResponse({ ok: false, error: 'Unsupported application action.' }, { status: 400 })
    }
    return dashboardJsonResponse({ ok: true, data: await saveApplicationEntry(body.entry) })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Application workspace update failed.'
    return dashboardJsonResponse({ ok: false, error: message }, { status: error instanceof SyntaxError ? 400 : 422 })
  }
}
