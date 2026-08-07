import { NextResponse } from 'next/server'

import {
  DASHBOARD_REMEMBERED_SESSION_MAX_AGE_SECONDS,
  DASHBOARD_SESSION_COOKIE,
  DASHBOARD_SESSION_MAX_AGE_SECONDS,
  DASHBOARD_SESSION_SECRET_ENV_VAR,
  applyDashboardPrivateHeaders,
  dashboardSessionSecretFromEnv,
  dashboardTokenFromEnv,
  isDashboardTokenAuthorized,
  isSameOriginRequest,
  legacyDashboardSessionCookieName,
} from '@/lib/server/auth'
import { createDashboardSession } from '@/lib/server/session'

export const runtime = 'nodejs'

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

  const secret = dashboardSessionSecretFromEnv()
  if (secret.length < 32) {
    return applyDashboardPrivateHeaders(
      NextResponse.json(
        { ok: false, error: `${DASHBOARD_SESSION_SECRET_ENV_VAR} is not configured with a valid secret.` },
        { status: 503 },
      ),
    )
  }

  let body: { token?: string; email?: string; password?: string; remember?: boolean } = {}
  try {
    body = (await request.json()) as typeof body
  } catch {
    return applyDashboardPrivateHeaders(
      NextResponse.json({ ok: false, error: 'Invalid login request.' }, { status: 400 }),
    )
  }

  if (body.email || body.password) {
    return applyDashboardPrivateHeaders(
      NextResponse.json(
        { ok: false, error: 'Dashboard login requires the local dashboard token.' },
        { status: 400 },
      ),
    )
  }

  const suppliedToken = typeof body.token === 'string' && body.token.length <= 4096
    ? body.token.trim()
    : ''
  if (!isDashboardTokenAuthorized(expectedToken, suppliedToken)) {
    return applyDashboardPrivateHeaders(
      NextResponse.json({ ok: false, error: 'Invalid dashboard token.' }, { status: 401 }),
    )
  }

  const maxAge = body.remember
    ? DASHBOARD_REMEMBERED_SESSION_MAX_AGE_SECONDS
    : DASHBOARD_SESSION_MAX_AGE_SECONDS
  const expiresAt = Date.now() + maxAge * 1000
  const session = createDashboardSession(secret, {
    version: 1,
    subject: 'local-user',
    expiresAt,
  })
  const response = NextResponse.json({ ok: true })
  response.cookies.set({
    name: DASHBOARD_SESSION_COOKIE,
    value: session,
    httpOnly: true,
    sameSite: 'strict',
    secure: process.env.NODE_ENV === 'production',
    maxAge,
    path: '/',
  })
  // Expire the legacy cookie so an old browser does not retain misleading state.
  response.cookies.set({
    name: legacyDashboardSessionCookieName(),
    value: '',
    httpOnly: true,
    sameSite: 'strict',
    maxAge: 0,
    expires: new Date(0),
    path: '/',
  })
  return applyDashboardPrivateHeaders(response)
}
