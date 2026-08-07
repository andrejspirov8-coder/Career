import { afterEach, describe, expect, it } from 'vitest'
import { createDashboardSession } from './server/session'
import {
  dashboardAuthErrorResponse,
  dashboardAuthFailure,
  dashboardTokenFromEnv,
  dashboardJsonResponse,
  dashboardMutationAuthErrorResponse,
  dashboardTokenFromRequest,
  isDashboardHeadersAuthorized,
  isDashboardTokenAuthorized,
  isSameOriginLogoutRequest,
  isSameOriginRequest,
  safeDashboardNextPath,
  DASHBOARD_SESSION_COOKIE,
} from './dashboard-auth'

describe('dashboard recruiter API auth', () => {
  it('rejects requests when the local dashboard token is not configured', () => {
    expect(isDashboardTokenAuthorized('', null)).toBe(false)
    expect(dashboardAuthFailure('', null)).toMatchObject({
      status: 503,
      error: 'CAREER_DASHBOARD_TOKEN is not configured.',
    })
  })

  it('rejects missing or wrong request tokens', () => {
    expect(isDashboardTokenAuthorized('secret', null)).toBe(false)
    expect(isDashboardTokenAuthorized('secret', 'wrong')).toBe(false)
    expect(dashboardAuthFailure('secret', 'wrong')).toMatchObject({
      status: 401,
      error: 'Missing or invalid dashboard token.',
    })
  })

  it('rejects all headers when the expected token is empty', () => {
    expect(isDashboardHeadersAuthorized('', new Headers())).toBe(false)
    expect(isDashboardHeadersAuthorized('', new Headers({ 'x-career-dashboard-token': 'dev-disabled-auth' }))).toBe(false)
  })

  it('does not invent an authentication token when configuration is missing', () => {
    expect(dashboardTokenFromEnv({})).toBe('')
    expect(dashboardTokenFromEnv({ CAREER_DASHBOARD_TOKEN: '  secret  ' })).toBe('secret')
  })

  it('accepts either the dashboard token header or a bearer token', () => {
    const headerRequest = new Request('http://127.0.0.1/api/recruiter/overview', {
      headers: { 'x-career-dashboard-token': 'secret' },
    })
    const bearerRequest = new Request('http://127.0.0.1/api/recruiter/overview', {
      headers: { Authorization: 'Bearer secret' },
    })

    expect(dashboardTokenFromRequest(headerRequest)).toBe('secret')
    expect(dashboardTokenFromRequest(bearerRequest)).toBe('secret')
    expect(isDashboardTokenAuthorized('secret', dashboardTokenFromRequest(headerRequest))).toBe(true)
  })

  it('accepts only a valid signed session cookie', () => {
    process.env.CAREER_DASHBOARD_TOKEN = 'secret'
    process.env.CAREER_DASHBOARD_SESSION_SECRET = 'a'.repeat(32)
    const session = createDashboardSession('a'.repeat(32), {
      version: 1,
      subject: 'local-user',
      expiresAt: Date.now() + 60_000,
    })
    const validRequest = new Request('http://127.0.0.1/api/recruiter/overview', {
      headers: { cookie: `${DASHBOARD_SESSION_COOKIE}=${session}` },
    })
    const arbitraryRequest = new Request('http://127.0.0.1/api/recruiter/overview', {
      headers: { cookie: `${DASHBOARD_SESSION_COOKIE}=arbitrary` },
    })
    const oldCookieRequest = new Request('http://127.0.0.1/api/recruiter/overview', {
      headers: { cookie: 'career_sb_token=e2e-token' },
    })
    const noCookieRequest = new Request('http://127.0.0.1/api/recruiter/overview')

    expect(dashboardAuthErrorResponse(validRequest)).toBeNull()
    expect(dashboardAuthErrorResponse(arbitraryRequest)?.status).toBe(401)
    expect(dashboardAuthErrorResponse(oldCookieRequest)?.status).toBe(401)
    expect(dashboardAuthErrorResponse(noCookieRequest)?.status).toBe(401)
  })

  afterEach(() => {
    delete process.env.CAREER_DASHBOARD_TOKEN
    delete process.env.CAREER_DASHBOARD_SESSION_SECRET
  })

  it('requires same-origin browser mutations while retaining header-token clients', async () => {
    process.env.CAREER_DASHBOARD_TOKEN = 'secret'
    const noAuth = new Request('http://127.0.0.1:3000/api/recruiter/actions', {
      method: 'POST',
      headers: {
        origin: 'https://attacker.example',
      },
    })
    const tokenClient = new Request('http://127.0.0.1:3000/api/recruiter/actions', {
      method: 'POST',
      headers: { 'x-career-dashboard-token': 'secret' },
    })

    const denied = dashboardMutationAuthErrorResponse(noAuth)
    expect(denied?.status).toBe(401)
    await expect(denied?.json()).resolves.toMatchObject({ ok: false })
    expect(dashboardMutationAuthErrorResponse(tokenClient)).toBeNull()
    delete process.env.CAREER_DASHBOARD_TOKEN
  })

  it('uses the public host header when Next.js supplies an internal request URL', () => {
    const request = new Request('http://localhost:3000/api/auth/logout', {
      method: 'POST',
      headers: {
        host: '127.0.0.1:3000',
        origin: 'http://127.0.0.1:3000',
      },
    })

    expect(isSameOriginRequest(request)).toBe(true)
  })

  it('allows the fixed logout header used by the same-origin browser client', () => {
    const logoutRequest = new Request('http://localhost:3000/api/auth/logout', {
      method: 'POST',
      headers: {
        'x-career-dashboard-action': 'logout',
      },
    })
    const ordinaryCrossSiteRequest = new Request('http://127.0.0.1:3000/api/auth/logout', {
      method: 'POST',
      headers: {
        origin: 'https://attacker.example',
        'sec-fetch-site': 'cross-site',
      },
    })

    expect(isSameOriginLogoutRequest(logoutRequest)).toBe(true)
    expect(isSameOriginLogoutRequest(ordinaryCrossSiteRequest)).toBe(false)
  })

  it('keeps login redirects inside the local dashboard', () => {
    expect(safeDashboardNextPath('/automation?view=recent')).toBe('/automation?view=recent')
    expect(safeDashboardNextPath('//attacker.example/path')).toBe('/')
    expect(safeDashboardNextPath('/\\attacker.example/path')).toBe('/')
    expect(safeDashboardNextPath('https://attacker.example/path')).toBe('/')
  })

  it('marks private JSON responses as non-cacheable', () => {
    const response = dashboardJsonResponse({ ok: true })

    expect(response.headers.get('cache-control')).toContain('no-store')
    expect(response.headers.get('pragma')).toBe('no-cache')
    expect(response.headers.get('x-content-type-options')).toBe('nosniff')
  })
})
