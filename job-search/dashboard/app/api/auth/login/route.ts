import { NextResponse } from 'next/server'

import {
  DASHBOARD_REMEMBERED_SESSION_MAX_AGE_SECONDS,
  DASHBOARD_SESSION_COOKIE,
  DASHBOARD_SESSION_MAX_AGE_SECONDS,
  applyDashboardPrivateHeaders,
  dashboardSessionValue,
  dashboardTokenFromEnv,
  isDashboardTokenAuthorized,
  isSameOriginRequest,
} from '../../../../lib/server/auth'

export async function POST(request: Request) {
  const expectedToken = dashboardTokenFromEnv()
  if (!expectedToken) {
    return applyDashboardPrivateHeaders(
      NextResponse.json(
        { ok: false, error: 'CAREER_DASHBOARD_TOKEN is not configured.' },
        { status: 503 },
      ),
    )
  }

  if (!isSameOriginRequest(request)) {
    return applyDashboardPrivateHeaders(
      NextResponse.json({ ok: false, error: 'Login requires a same-origin request.' }, { status: 403 }),
    )
  }

  let suppliedToken = ''
  let remember = false
  try {
    const body = (await request.json()) as { token?: string; remember?: boolean }
    suppliedToken = typeof body.token === 'string' && body.token.length <= 4096 ? body.token.trim() : ''
    remember = body.remember === true
  } catch {
    return applyDashboardPrivateHeaders(
      NextResponse.json({ ok: false, error: 'Invalid login request.' }, { status: 400 }),
    )
  }

  if (!isDashboardTokenAuthorized(expectedToken, suppliedToken)) {
    return applyDashboardPrivateHeaders(
      NextResponse.json({ ok: false, error: 'Invalid dashboard token.' }, { status: 401 }),
    )
  }

  const maxAge = remember
    ? DASHBOARD_REMEMBERED_SESSION_MAX_AGE_SECONDS
    : DASHBOARD_SESSION_MAX_AGE_SECONDS
  const response = NextResponse.json({ ok: true })
  response.cookies.set({
    name: DASHBOARD_SESSION_COOKIE,
    value: dashboardSessionValue(expectedToken, undefined, maxAge),
    httpOnly: true,
    sameSite: 'strict',
    maxAge,
    path: '/',
  })
  return applyDashboardPrivateHeaders(response)
}
