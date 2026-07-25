import { applyDashboardPrivateHeaders, dashboardAuthErrorResponse } from '@/lib/server/auth'
import { getOpportunityExport } from '@/lib/opportunity-data'

export const dynamic = 'force-dynamic'

export async function GET(request: Request) {
  const authError = dashboardAuthErrorResponse(request)
  if (authError) return authError

  try {
    const data = await getOpportunityExport()
    const date = new Date().toISOString().slice(0, 10)
    return applyDashboardPrivateHeaders(new Response(JSON.stringify(data, null, 2), {
      status: 200,
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Content-Disposition': `attachment; filename="career-data-${date}.json"`,
      },
    }))
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Export failed.'
    return applyDashboardPrivateHeaders(Response.json({ ok: false, error: message }, { status: 500 }))
  }
}
