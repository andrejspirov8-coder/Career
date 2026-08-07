import { cookies, headers } from 'next/headers'
import { redirect } from 'next/navigation'

import {
  DASHBOARD_SESSION_COOKIE,
  dashboardAuthDecision,
  dashboardSessionSecretFromEnv,
  dashboardTokenFromEnv,
  dashboardTokenFromHeaders,
  isDashboardTokenAuthorized,
} from './dashboard-auth'
import { verifyDashboardSession } from './server/session'

export async function isDashboardPageAuthenticated(): Promise<boolean> {
  const expectedToken = dashboardTokenFromEnv()
  if (!expectedToken) return false

  const [requestHeaders, cookieStore] = await Promise.all([headers(), cookies()])

  if (isDashboardTokenAuthorized(expectedToken, dashboardTokenFromHeaders(requestHeaders))) return true

  const sessionValue = cookieStore.get(DASHBOARD_SESSION_COOKIE)?.value
  const secret = dashboardSessionSecretFromEnv()
  return Boolean(sessionValue && secret.length >= 32 && verifyDashboardSession(sessionValue, secret))
}

export async function requireDashboardPageAuth(nextPath = '/'): Promise<void> {
  if (await isDashboardPageAuthenticated()) return

  const safeNextPath = nextPath.startsWith('/') && !nextPath.startsWith('//') ? nextPath : '/'
  redirect(`/login?next=${encodeURIComponent(safeNextPath)}`)
}
