import { dashboardJsonResponse, dashboardMutationAuthErrorResponse } from '@/lib/server/auth'
import { runPythonHelper } from '@/lib/server/python-bridge'

export const dynamic = 'force-dynamic'
export const maxDuration = 300

export async function POST(request: Request) {
  const authError = dashboardMutationAuthErrorResponse(request)
  if (authError) return authError

  try {
    const body = await request.json().catch(() => ({}))
    const configPath = body.config || 'config/opportunities.example.yaml'

    const data = await runPythonHelper('opportunityOrchestrate', [
      'daily-queue',
      '--config', configPath,
    ], {
      timeoutMs: 300_000,
      errorLabel: 'Daily queue pipeline',
    })

    return dashboardJsonResponse({ ok: true, data })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Pipeline failed.'
    return dashboardJsonResponse({ ok: false, error: message }, { status: 500 })
  }
}
