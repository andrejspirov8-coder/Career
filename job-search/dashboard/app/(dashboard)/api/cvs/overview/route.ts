import { dashboardAuthErrorResponse, dashboardJsonResponse } from '@/lib/server/auth'
import { getCvLibrary } from '@/lib/cv-data'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(request: Request) {
  const authError = dashboardAuthErrorResponse(request)
  if (authError) return authError
  return dashboardJsonResponse({ ok: true, data: await getCvLibrary() })
}
