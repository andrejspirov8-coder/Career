import { NextResponse } from 'next/server'

import { applyDashboardPrivateHeaders } from '@/lib/server/auth'
import { runFastApiEndpoint } from '@/lib/server/fastapi-bridge'

export const runtime = 'nodejs'

export async function POST(request: Request) {
  let body: { email?: string; password?: string } = {}
  try {
    body = (await request.json()) as typeof body
  } catch {
    return applyDashboardPrivateHeaders(
      NextResponse.json({ ok: false, error: 'Invalid signup request.' }, { status: 400 }),
    )
  }

  if (!body.email || !body.password) {
    return applyDashboardPrivateHeaders(
      NextResponse.json({ ok: false, error: 'Email and password are required.' }, { status: 400 }),
    )
  }

  try {
    const result = await runFastApiEndpoint<{ user_id: string; email: string }>(
      'auth/signup',
      { email: body.email, password: body.password },
      { timeoutMs: 10_000, errorLabel: 'Auth signup' },
    )
    return applyDashboardPrivateHeaders(
      NextResponse.json({ ok: true, email: result.email }),
    )
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Signup failed'
    return applyDashboardPrivateHeaders(
      NextResponse.json({ ok: false, error: message }, { status: 409 }),
    )
  }
}
