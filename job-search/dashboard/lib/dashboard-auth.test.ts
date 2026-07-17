import { describe, expect, it } from 'vitest'
import {
  DASHBOARD_REMEMBERED_SESSION_MAX_AGE_SECONDS,
  DASHBOARD_SESSION_COOKIE,
  DASHBOARD_SESSION_MAX_AGE_SECONDS,
  dashboardAuthFailure,
  dashboardCookieFromHeaders,
  dashboardJsonResponse,
  dashboardMutationAuthErrorResponse,
  dashboardSessionValue,
  dashboardTokenFromRequest,
  isDashboardHeadersAuthorized,
  isDashboardSessionAuthorized,
  isDashboardTokenAuthorized,
  isSameOriginLogoutRequest,
  isSameOriginRequest,
  safeDashboardNextPath,
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

  it('accepts a derived session cookie without storing the original token', () => {
    const sessionValue = dashboardSessionValue('secret')
    const headers = new Headers({ cookie: `${DASHBOARD_SESSION_COOKIE}=${sessionValue}` })

    expect(sessionValue).not.toContain('secret')
    expect(dashboardCookieFromHeaders(headers)).toBe(sessionValue)
    expect(isDashboardSessionAuthorized('secret', sessionValue)).toBe(true)
    expect(isDashboardSessionAuthorized('secret', 'wrong')).toBe(false)
    expect(isDashboardHeadersAuthorized('secret', headers)).toBe(true)
  })

  it('rejects a copied session value after eight hours', () => {
    const now = 2_000_000_000
    const valid = dashboardSessionValue('secret', now - DASHBOARD_SESSION_MAX_AGE_SECONDS)
    const expired = dashboardSessionValue('secret', now - DASHBOARD_SESSION_MAX_AGE_SECONDS - 1)

    expect(isDashboardSessionAuthorized('secret', valid, now)).toBe(true)
    expect(isDashboardSessionAuthorized('secret', expired, now)).toBe(false)
  })

  it('supports an explicitly remembered browser for 30 days', () => {
    const now = 2_000_000_000
    const valid = dashboardSessionValue(
      'secret',
      now - DASHBOARD_REMEMBERED_SESSION_MAX_AGE_SECONDS,
      DASHBOARD_REMEMBERED_SESSION_MAX_AGE_SECONDS,
    )
    const expired = dashboardSessionValue(
      'secret',
      now - DASHBOARD_REMEMBERED_SESSION_MAX_AGE_SECONDS - 1,
      DASHBOARD_REMEMBERED_SESSION_MAX_AGE_SECONDS,
    )

    expect(isDashboardSessionAuthorized('secret', valid, now)).toBe(true)
    expect(isDashboardSessionAuthorized('secret', expired, now)).toBe(false)
    expect(dashboardSessionValue('secret', now, 365 * 24 * 60 * 60)).toBe('')
  })

  it('requires same-origin browser mutations while retaining header-token clients', async () => {
    process.env.CAREER_DASHBOARD_TOKEN = 'secret'
    const sessionValue = dashboardSessionValue('secret')
    const crossOrigin = new Request('http://127.0.0.1:3000/api/recruiter/actions', {
      method: 'POST',
      headers: {
        cookie: `${DASHBOARD_SESSION_COOKIE}=${sessionValue}`,
        origin: 'https://attacker.example',
      },
    })
    const tokenClient = new Request('http://127.0.0.1:3000/api/recruiter/actions', {
      method: 'POST',
      headers: { 'x-career-dashboard-token': 'secret' },
    })

    const denied = dashboardMutationAuthErrorResponse(crossOrigin)
    expect(denied?.status).toBe(403)
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
