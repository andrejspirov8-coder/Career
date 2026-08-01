import { cookies, headers } from 'next/headers'
import { redirect } from 'next/navigation'

import {
  DASHBOARD_SESSION_SUPABASE_TOKEN_COOKIE,
  dashboardTokenFromEnv,
  dashboardTokenFromHeaders,
  isDashboardTokenAuthorized,
} from './dashboard-auth'

export async function isDashboardPageAuthenticated(): Promise<boolean> {
  const expectedToken = dashboardTokenFromEnv()
  if (!expectedToken) return false

  const [requestHeaders, cookieStore] = await Promise.all([headers(), cookies()])

  if (isDashboardTokenAuthorized(expectedToken, dashboardTokenFromHeaders(requestHeaders))) return true

  const sbToken = cookieStore.get(DASHBOARD_SESSION_SUPABASE_TOKEN_COOKIE)?.value
  if (sbToken) return true

  return false
}

export async function requireDashboardPageAuth(nextPath = '/'): Promise<void> {
  if (await isDashboardPageAuthenticated()) return

  const safeNextPath = nextPath.startsWith('/') && !nextPath.startsWith('//') ? nextPath : '/'
  redirect(`/login?next=${encodeURIComponent(safeNextPath)}`)
}
