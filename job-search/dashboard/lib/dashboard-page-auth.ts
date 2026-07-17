import { cookies, headers } from 'next/headers'
import { redirect } from 'next/navigation'

import {
  DASHBOARD_SESSION_COOKIE,
  dashboardTokenFromEnv,
  dashboardTokenFromHeaders,
  isDashboardSessionAuthorized,
  isDashboardTokenAuthorized,
} from './dashboard-auth'

export async function isDashboardPageAuthenticated(): Promise<boolean> {
  const expectedToken = dashboardTokenFromEnv()
  if (!expectedToken) return false

  const [requestHeaders, cookieStore] = await Promise.all([headers(), cookies()])
  return (
    isDashboardTokenAuthorized(expectedToken, dashboardTokenFromHeaders(requestHeaders)) ||
    isDashboardSessionAuthorized(expectedToken, cookieStore.get(DASHBOARD_SESSION_COOKIE)?.value || null)
  )
}

export async function requireDashboardPageAuth(nextPath = '/'): Promise<void> {
  if (await isDashboardPageAuthenticated()) return

  const safeNextPath = nextPath.startsWith('/') && !nextPath.startsWith('//') ? nextPath : '/'
  redirect(`/login?next=${encodeURIComponent(safeNextPath)}`)
}
