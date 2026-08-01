import { dashboardAuthErrorResponse, dashboardJsonResponse } from '@/lib/server/auth'
import { getSetupChecklist } from '@/lib/setup-checklist'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(request: Request) {
  const authError = dashboardAuthErrorResponse(request)
  if (authError) return authError

  try {
    return dashboardJsonResponse({ ok: true, data: await getSetupChecklist() })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Setup checklist is unavailable.'
    return dashboardJsonResponse({ ok: false, error: message }, { status: 500 })
  }
}
