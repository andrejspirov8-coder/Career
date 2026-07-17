import { createHmac, timingSafeEqual } from 'node:crypto'

export const DASHBOARD_TOKEN_ENV_VAR = 'CAREER_DASHBOARD_TOKEN'
export const DASHBOARD_TOKEN_HEADER = 'x-career-dashboard-token'
export const DASHBOARD_SESSION_COOKIE = 'career_dashboard_session'
export const DASHBOARD_SESSION_MAX_AGE_SECONDS = 8 * 60 * 60
export const DASHBOARD_REMEMBERED_SESSION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60

const dashboardSessionPurpose = 'career-dashboard-session-v2'
const allowedSessionMaxAges = new Set([
  DASHBOARD_SESSION_MAX_AGE_SECONDS,
  DASHBOARD_REMEMBERED_SESSION_MAX_AGE_SECONDS,
])

export type DashboardAuthFailure = {
  status: 401 | 503
  error: string
}

export function applyDashboardPrivateHeaders<T extends Response>(response: T): T {
  response.headers.set('Cache-Control', 'no-store, max-age=0')
  response.headers.set('Pragma', 'no-cache')
  response.headers.set('X-Content-Type-Options', 'nosniff')
  return response
}

export function dashboardJsonResponse(data: unknown, init: ResponseInit = {}): Response {
  return applyDashboardPrivateHeaders(Response.json(data, init))
}

export function dashboardTokenFromEnv(env: NodeJS.ProcessEnv = process.env): string {
  return (env[DASHBOARD_TOKEN_ENV_VAR] || '').trim()
}

export function safeDashboardNextPath(value: unknown): string {
  if (
    typeof value !== 'string' ||
    !value.startsWith('/') ||
    value.startsWith('//') ||
    value.includes('\\') ||
    /[\u0000-\u001f\u007f]/.test(value)
  ) {
    return '/'
  }

  try {
    const base = new URL('http://career-dashboard.local')
    const candidate = new URL(value, base)
    if (candidate.origin !== base.origin) return '/'
    return `${candidate.pathname}${candidate.search}`
  } catch {
    return '/'
  }
}

export function dashboardTokenFromHeaders(headers: Headers): string | null {
  const headerToken = headers.get(DASHBOARD_TOKEN_HEADER)?.trim()
  if (headerToken) return headerToken

  const authHeader = headers.get('authorization')?.trim() || ''
  const match = /^Bearer\s+(.+)$/i.exec(authHeader)
  return match?.[1]?.trim() || null
}

export function dashboardTokenFromRequest(request: Request): string | null {
  return dashboardTokenFromHeaders(request.headers)
}

export function dashboardSessionValue(
  expectedToken: string,
  issuedAtSeconds = Math.floor(Date.now() / 1000),
  maxAgeSeconds = DASHBOARD_SESSION_MAX_AGE_SECONDS,
): string {
  if (!expectedToken || !allowedSessionMaxAges.has(maxAgeSeconds)) return ''
  const issuedAt = Math.floor(issuedAtSeconds)
  const signature = createHmac('sha256', expectedToken)
    .update(`${dashboardSessionPurpose}:${issuedAt}:${maxAgeSeconds}`)
    .digest('hex')
  return `${issuedAt}.${maxAgeSeconds}.${signature}`
}

export function dashboardCookieFromHeaders(headers: Headers): string | null {
  const cookieHeader = headers.get('cookie') || ''
  for (const part of cookieHeader.split(';')) {
    const [rawName, ...rawValue] = part.trim().split('=')
    if (rawName !== DASHBOARD_SESSION_COOKIE) continue
    const value = rawValue.join('=').trim()
    return value ? decodeURIComponent(value) : null
  }
  return null
}

function safeStringEqual(expected: string, candidate: string | null): boolean {
  if (!expected || !candidate) return false
  const expectedBuffer = Buffer.from(expected)
  const candidateBuffer = Buffer.from(candidate)
  return expectedBuffer.length === candidateBuffer.length && timingSafeEqual(expectedBuffer, candidateBuffer)
}

export function isDashboardTokenAuthorized(expectedToken: string, requestToken: string | null): boolean {
  return safeStringEqual(expectedToken, requestToken)
}

export function isDashboardSessionAuthorized(
  expectedToken: string,
  sessionValue: string | null,
  nowSeconds = Math.floor(Date.now() / 1000),
): boolean {
  if (!sessionValue) return false
  const [rawIssuedAt, rawMaxAge, signature, ...extra] = sessionValue.split('.')
  if (!rawIssuedAt || !rawMaxAge || !signature || extra.length) return false
  const issuedAt = Number(rawIssuedAt)
  const maxAge = Number(rawMaxAge)
  if (!Number.isSafeInteger(issuedAt) || !Number.isSafeInteger(maxAge) || !allowedSessionMaxAges.has(maxAge)) {
    return false
  }
  const age = Math.floor(nowSeconds) - issuedAt
  if (age < 0 || age > maxAge) return false
  return safeStringEqual(dashboardSessionValue(expectedToken, issuedAt, maxAge), sessionValue)
}

export function isDashboardHeadersAuthorized(expectedToken: string, headers: Headers): boolean {
  return (
    isDashboardTokenAuthorized(expectedToken, dashboardTokenFromHeaders(headers)) ||
    isDashboardSessionAuthorized(expectedToken, dashboardCookieFromHeaders(headers))
  )
}

export function isSameOriginRequest(request: Request): boolean {
  const origin = request.headers.get('origin')
  if (!origin) return false

  try {
    const originUrl = new URL(origin)
    const requestUrl = new URL(request.url)
    const host = request.headers.get('x-forwarded-host') || request.headers.get('host') || requestUrl.host
    const protocol =
      request.headers.get('x-forwarded-proto')?.split(',')[0]?.trim() || requestUrl.protocol.replace(/:$/, '')
    return originUrl.host === host && originUrl.protocol === `${protocol}:`
  } catch {
    return false
  }
}

export function isSameOriginLogoutRequest(request: Request): boolean {
  // The non-simple header cannot be sent by a cross-origin form and causes a
  // browser CORS preflight for cross-origin fetches; this server grants none.
  return (
    isSameOriginRequest(request) ||
    request.headers.get('x-career-dashboard-action') === 'logout'
  )
}

export function dashboardAuthFailure(expectedToken: string, requestToken: string | null): DashboardAuthFailure | null {
  if (!expectedToken) {
    return {
      status: 503,
      error: `${DASHBOARD_TOKEN_ENV_VAR} is not configured.`,
    }
  }

  if (!isDashboardTokenAuthorized(expectedToken, requestToken)) {
    return {
      status: 401,
      error: 'Missing or invalid dashboard token.',
    }
  }

  return null
}

export function dashboardAuthErrorResponse(request: Request): Response | null {
  const expectedToken = dashboardTokenFromEnv()
  const failure = dashboardAuthFailure(
    expectedToken,
    isDashboardHeadersAuthorized(expectedToken, request.headers) ? expectedToken : null,
  )
  if (!failure) return null

  return dashboardJsonResponse({ ok: false, error: failure.error }, { status: failure.status })
}

export function dashboardMutationAuthErrorResponse(request: Request): Response | null {
  const authError = dashboardAuthErrorResponse(request)
  if (authError) return authError

  if (dashboardTokenFromRequest(request)) return null

  if (!isSameOriginRequest(request)) {
    return dashboardJsonResponse(
      { ok: false, error: 'Dashboard action requires a same-origin request.' },
      { status: 403 },
    )
  }
  return null
}
