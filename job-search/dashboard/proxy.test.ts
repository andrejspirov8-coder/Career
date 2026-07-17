import { describe, expect, it } from 'vitest'

import { isCvDocumentPath, securityPolicy } from './proxy'

describe('dashboard content security policy', () => {
  it('allows the Next.js debugger only during local development', () => {
    expect(securityPolicy('test-nonce', 'development')).toContain("'unsafe-eval'")
  })

  it('keeps unsafe evaluation blocked in production', () => {
    const policy = securityPolicy('test-nonce', 'production')

    expect(policy).not.toContain("'unsafe-eval'")
    expect(policy).toContain("object-src 'none'")
    expect(policy).toContain("frame-ancestors 'none'")
  })

  it('allows only protected CV documents to render in the same dashboard', () => {
    expect(isCvDocumentPath('/api/cvs/operations-management/visual')).toBe(true)
    expect(isCvDocumentPath('/api/cvs/operations-management/ats')).toBe(true)
    expect(isCvDocumentPath('/api/cvs/overview')).toBe(false)
    expect(isCvDocumentPath('/api/opportunities/overview')).toBe(false)

    expect(securityPolicy('test-nonce', 'production', true)).toContain("frame-ancestors 'self'")
  })
})
