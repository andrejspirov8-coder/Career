import { NextResponse } from 'next/server'

import {
  DASHBOARD_SESSION_COOKIE,
  applyDashboardPrivateHeaders,
  isSameOriginLogoutRequest,
} from '../../../../lib/server/auth'

export async function POST(request: Request) {
  if (!isSameOriginLogoutRequest(request)) {
    return applyDashboardPrivateHeaders(
      NextResponse.json({ ok: false, error: 'Logout requires a same-origin request.' }, { status: 403 }),
    )
  }

  const response = NextResponse.json({ ok: true })
  response.cookies.set({
    name: DASHBOARD_SESSION_COOKIE,
    value: '',
    httpOnly: true,
    sameSite: 'strict',
    maxAge: 0,
    expires: new Date(0),
    path: '/',
  })
  return applyDashboardPrivateHeaders(response)
}
