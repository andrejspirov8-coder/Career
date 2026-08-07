import { timingSafeEqual } from 'node:crypto'

import { verifyDashboardSession } from './session'

export const DASHBOARD_TOKEN_ENV_VAR = 'CAREER_DASHBOARD_TOKEN'
export const DASHBOARD_SESSION_SECRET_ENV_VAR = 'CAREER_DASHBOARD_SESSION_SECRET'
export const DASHBOARD_TOKEN_HEADER = 'x-career-dashboard-token'
export const DASHBOARD_SESSION_COOKIE = 'career_dashboard_session'
const LEGACY_SESSION_COOKIE = ['career', 'sb_token'].join('_')
export const DASHBOARD_REMEMBERED_SESSION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
export const DASHBOARD_SESSION_MAX_AGE_SECONDS = 8 * 60 * 60

export type DashboardAuthFailure = {
  status: 401 | 503
  error: string
}

type DashboardAuthDecision =
  | { authorized: true; via: 'header' | 'session' }
  | ({ authorized: false } & DashboardAuthFailure)

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

export function dashboardSessionSecretFromEnv(env: NodeJS.ProcessEnv = process.env): string {
  return (env[DASHBOARD_SESSION_SECRET_ENV_VAR] || '').trim()
}

export function dashboardAuthConfigured(env: NodeJS.ProcessEnv = process.env): boolean {
  return Boolean(dashboardTokenFromEnv(env) && dashboardSessionSecretFromEnv(env).length >= 32)
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

function safeStringEqual(expected: string, candidate: string | null): boolean {
  if (!expected || !candidate) return false
  const expectedBuffer = Buffer.from(expected)
  const candidateBuffer = Buffer.from(candidate)
  return expectedBuffer.length === candidateBuffer.length && timingSafeEqual(expectedBuffer, candidateBuffer)
}

export function isDashboardTokenAuthorized(expectedToken: string, requestToken: string | null): boolean {
  return safeStringEqual(expectedToken, requestToken)
}

export function isDashboardHeadersAuthorized(expectedToken: string, headers: Headers): boolean {
  return isDashboardTokenAuthorized(expectedToken, dashboardTokenFromHeaders(headers))
}

function cookieValue(headers: Headers, name: string): string | null {
  const raw = headers.get('cookie') || ''
  for (const part of raw.split(';')) {
    const separator = part.indexOf('=')
    if (separator < 0) continue
    if (part.slice(0, separator).trim() === name) return part.slice(separator + 1).trim()
  }
  return null
}

export function dashboardAuthDecision(
  request: Request,
  env: NodeJS.ProcessEnv = process.env,
): DashboardAuthDecision {
  const expectedToken = dashboardTokenFromEnv(env)
  if (!expectedToken) {
    return {
      authorized: false,
      status: 503,
      error: `${DASHBOARD_TOKEN_ENV_VAR} is not configured.`,
    }
  }

  if (isDashboardHeadersAuthorized(expectedToken, request.headers)) {
    return { authorized: true, via: 'header' }
  }

  const sessionValue = cookieValue(request.headers, DASHBOARD_SESSION_COOKIE)
  if (sessionValue) {
    const secret = dashboardSessionSecretFromEnv(env)
    if (secret.length < 32) {
      return {
        authorized: false,
        status: 503,
        error: `${DASHBOARD_SESSION_SECRET_ENV_VAR} is not configured with a valid secret.`,
      }
    }
    if (verifyDashboardSession(sessionValue, secret)) {
      return { authorized: true, via: 'session' }
    }
  }

  return {
    authorized: false,
    status: 401,
    error: 'Missing or invalid dashboard authentication.',
  }
}

export function isDashboardRequestAuthorized(
  request: Request,
  env: NodeJS.ProcessEnv = process.env,
): boolean {
  return dashboardAuthDecision(request, env).authorized
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
  const decision = dashboardAuthDecision(request)
  if (decision.authorized) return null
  return dashboardJsonResponse(
    { ok: false, error: decision.error },
    { status: decision.status },
  )
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

export function legacyDashboardSessionCookieName(): string {
  return LEGACY_SESSION_COOKIE
}
