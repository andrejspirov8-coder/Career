import { NextResponse } from 'next/server'

import {
  DASHBOARD_REMEMBERED_SESSION_MAX_AGE_SECONDS,
  DASHBOARD_SESSION_MAX_AGE_SECONDS,
  DASHBOARD_SESSION_SUPABASE_TOKEN_COOKIE,
  applyDashboardPrivateHeaders,
  dashboardTokenFromEnv,
  isDashboardTokenAuthorized,
  isSameOriginRequest,
} from '@/lib/server/auth'
import { runFastApiEndpoint } from '@/lib/server/fastapi-bridge'

export const runtime = 'nodejs'

async function loginWithBackend(
  body: { email: string; password: string; remember?: boolean },
) {
  const { remember } = body
  const maxAge = remember
    ? DASHBOARD_REMEMBERED_SESSION_MAX_AGE_SECONDS
    : DASHBOARD_SESSION_MAX_AGE_SECONDS

  const result = await runFastApiEndpoint<{
    user_id: string
    email: string
    supabase_access_token?: string | null
  }>('auth/login', { email: body.email, password: body.password }, {
    timeoutMs: 10_000,
    errorLabel: 'Auth login',
  })

  const response = NextResponse.json({ ok: true })

  if (result.supabase_access_token) {
    response.cookies.set({
      name: DASHBOARD_SESSION_SUPABASE_TOKEN_COOKIE,
      value: result.supabase_access_token,
      httpOnly: true,
      sameSite: 'strict',
      maxAge,
      path: '/',
    })
  }

  return applyDashboardPrivateHeaders(response)
}

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

  let body: { token?: string; email?: string; password?: string; remember?: boolean } = {}
  try {
    body = (await request.json()) as typeof body
  } catch {
    return applyDashboardPrivateHeaders(
      NextResponse.json({ ok: false, error: 'Invalid login request.' }, { status: 400 }),
    )
  }

  if (body.email && body.password) {
    try {
      return await loginWithBackend({ email: body.email, password: body.password, remember: body.remember })
    } catch {
      return applyDashboardPrivateHeaders(
        NextResponse.json({ ok: false, error: 'Invalid email or password' }, { status: 401 }),
      )
    }
  }

  const suppliedToken =
    typeof body.token === 'string' && body.token.length <= 4096 ? body.token.trim() : ''
  if (!isDashboardTokenAuthorized(expectedToken, suppliedToken)) {
    return applyDashboardPrivateHeaders(
      NextResponse.json({ ok: false, error: 'Invalid dashboard token.' }, { status: 401 }),
    )
  }

  const maxAge = body.remember
    ? DASHBOARD_REMEMBERED_SESSION_MAX_AGE_SECONDS
    : DASHBOARD_SESSION_MAX_AGE_SECONDS
  const response = NextResponse.json({ ok: true })
  response.cookies.set({
    name: DASHBOARD_SESSION_SUPABASE_TOKEN_COOKIE,
    value: suppliedToken,
    httpOnly: true,
    sameSite: 'strict',
    maxAge,
    path: '/',
  })
  return applyDashboardPrivateHeaders(response)
}
