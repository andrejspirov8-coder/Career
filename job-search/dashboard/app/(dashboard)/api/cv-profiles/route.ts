import { dashboardAuthErrorResponse, dashboardJsonResponse, dashboardMutationAuthErrorResponse } from '@/lib/server/auth'
import { getCvProfiles, saveCvProfiles } from '@/lib/cv-profiles'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(request: Request) {
  const authError = dashboardAuthErrorResponse(request)
  if (authError) return authError

  try {
    return dashboardJsonResponse({ ok: true, data: await getCvProfiles() })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'CV profiles are unavailable.'
    return dashboardJsonResponse({ ok: false, error: message }, { status: 500 })
  }
}

export async function POST(request: Request) {
  const authError = dashboardMutationAuthErrorResponse(request)
  if (authError) return authError

  try {
    const body = (await request.json()) as { action?: unknown; profiles?: unknown }
    if (body.action === 'save') {
      return dashboardJsonResponse({ ok: true, data: await saveCvProfiles(body.profiles) })
    }
    return dashboardJsonResponse({ ok: false, error: 'Unsupported CV profiles action.' }, { status: 400 })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'CV profiles update failed.'
    const status = error instanceof SyntaxError ? 400 : 422
    return dashboardJsonResponse({ ok: false, error: message }, { status })
  }
}
