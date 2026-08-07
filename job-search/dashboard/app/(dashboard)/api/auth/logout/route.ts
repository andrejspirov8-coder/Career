import { NextResponse } from 'next/server'

import {
  DASHBOARD_SESSION_COOKIE,
  applyDashboardPrivateHeaders,
  isSameOriginLogoutRequest,
  legacyDashboardSessionCookieName,
} from '@/lib/server/auth'

export const runtime = 'nodejs'

export async function POST(request: Request) {
  if (!isSameOriginLogoutRequest(request)) {
    return applyDashboardPrivateHeaders(
      NextResponse.json({ ok: false, error: 'Logout requires a same-origin request.' }, { status: 403 }),
    )
  }

  const response = NextResponse.json({ ok: true })
  for (const name of [DASHBOARD_SESSION_COOKIE, legacyDashboardSessionCookieName()]) {
    response.cookies.set({
      name,
      value: '',
      httpOnly: true,
      sameSite: 'strict',
      maxAge: 0,
      expires: new Date(0),
      path: '/',
    })
  }
  return applyDashboardPrivateHeaders(response)
}
