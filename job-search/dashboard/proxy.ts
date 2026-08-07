import { randomBytes } from 'node:crypto'

import type { NextRequest } from 'next/server'
import { NextResponse } from 'next/server'

import { isDashboardRequestAuthorized } from './lib/dashboard-auth'

export function isCvDocumentPath(pathname: string): boolean {
  return /^\/api\/cvs\/[^/]+\/(visual|ats)$/.test(pathname)
}

export function securityPolicy(
  nonce: string,
  environment = process.env.NODE_ENV,
  allowSameOriginFrame = false,
): string {
  const scriptSources = ["'self'", `'nonce-${nonce}'`, "'strict-dynamic'"]
  if (environment === 'development') {
    scriptSources.push("'unsafe-eval'")
  }

  return [
    "default-src 'self'",
    `script-src ${scriptSources.join(' ')}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    "connect-src 'self'",
    "frame-src 'self' blob:",
    "object-src 'none'",
    "worker-src 'self' blob:",
    "base-uri 'self'",
    "form-action 'self'",
    `frame-ancestors ${allowSameOriginFrame ? "'self'" : "'none'"}`,
  ].join('; ')
}

function secureResponse(
  response: NextResponse,
  policy: string,
  allowSameOriginFrame: boolean,
): NextResponse {
  response.headers.set('Cache-Control', 'no-store, max-age=0')
  response.headers.set('Content-Security-Policy', policy)
  response.headers.set('Cross-Origin-Opener-Policy', 'same-origin')
  response.headers.set('Cross-Origin-Resource-Policy', 'same-origin')
  response.headers.set('Permissions-Policy', 'camera=(), microphone=(), geolocation=(), clipboard-write=(self)')
  response.headers.set('Referrer-Policy', 'no-referrer')
  response.headers.set('X-Content-Type-Options', 'nosniff')
  response.headers.set('X-Frame-Options', allowSameOriginFrame ? 'SAMEORIGIN' : 'DENY')
  return response
}

export function proxy(request: NextRequest) {
  const pathname = request.nextUrl.pathname
  const nonce = randomBytes(16).toString('base64')
  const allowSameOriginFrame = isCvDocumentPath(pathname)
  const policy = securityPolicy(nonce, process.env.NODE_ENV, allowSameOriginFrame)
  const requestHeaders = new Headers(request.headers)
  requestHeaders.set('Content-Security-Policy', policy)
  requestHeaders.set('x-nonce', nonce)

  if (pathname === '/login' || pathname.startsWith('/api/')) {
    return secureResponse(
      NextResponse.next({ request: { headers: requestHeaders } }),
      policy,
      allowSameOriginFrame,
    )
  }

  if (isDashboardRequestAuthorized(request)) {
    return secureResponse(
      NextResponse.next({ request: { headers: requestHeaders } }),
      policy,
      allowSameOriginFrame,
    )
  }

  const loginUrl = new URL('/login', request.url)
  loginUrl.searchParams.set('next', `${pathname}${request.nextUrl.search}`)
  return secureResponse(NextResponse.redirect(loginUrl), policy, allowSameOriginFrame)
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
}
