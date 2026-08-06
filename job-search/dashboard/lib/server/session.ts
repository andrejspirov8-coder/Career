import { createHmac, timingSafeEqual } from 'node:crypto'

export type DashboardSessionClaims = {
  version: 1
  subject: 'local-user'
  expiresAt: number
}

const MIN_SECRET_LENGTH = 32
const TOKEN_PART_PATTERN = /^[A-Za-z0-9_-]+$/

function requireSecret(secret: string): string {
  if (typeof secret !== 'string' || secret.trim().length < MIN_SECRET_LENGTH) {
    throw new Error('CAREER_DASHBOARD_SESSION_SECRET must contain at least 32 non-whitespace characters.')
  }
  return secret
}

function encode(value: string): string {
  return Buffer.from(value, 'utf8').toString('base64url')
}

function sign(payload: string, secret: string): string {
  return createHmac('sha256', requireSecret(secret)).update(payload).digest('base64url')
}

function validClaims(value: unknown): value is DashboardSessionClaims {
  if (!value || typeof value !== 'object') return false
  const claims = value as Partial<DashboardSessionClaims>
  return (
    claims.version === 1
    && claims.subject === 'local-user'
    && typeof claims.expiresAt === 'number'
    && Number.isFinite(claims.expiresAt)
  )
}

export function createDashboardSession(secret: string, claims: DashboardSessionClaims): string {
  requireSecret(secret)
  if (!validClaims(claims)) throw new Error('Invalid dashboard session claims.')
  const payload = encode(JSON.stringify(claims))
  return `${payload}.${sign(payload, secret)}`
}

export function verifyDashboardSession(
  value: string | null | undefined,
  secret: string,
  nowMs = Date.now(),
): DashboardSessionClaims | null {
  if (!value) return null
  try {
    requireSecret(secret)
    const parts = value.split('.')
    if (parts.length !== 2 || !parts.every((part) => TOKEN_PART_PATTERN.test(part))) return null

    const expected = Buffer.from(sign(parts[0], secret), 'utf8')
    const supplied = Buffer.from(parts[1], 'utf8')
    if (expected.length !== supplied.length || !timingSafeEqual(expected, supplied)) return null

    const claims = JSON.parse(Buffer.from(parts[0], 'base64url').toString('utf8')) as unknown
    if (!validClaims(claims) || claims.expiresAt <= nowMs) return null
    return claims
  } catch {
    return null
  }
}
