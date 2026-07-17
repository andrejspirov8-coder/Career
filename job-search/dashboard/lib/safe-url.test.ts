import { describe, expect, it } from 'vitest'

import { safeExternalHttpUrl } from './safe-url'

describe('safeExternalHttpUrl', () => {
  it('allows normal HTTP and HTTPS links', () => {
    expect(safeExternalHttpUrl('https://jobs.example/role?id=42')).toBe(
      'https://jobs.example/role?id=42',
    )
    expect(safeExternalHttpUrl('http://jobs.example/role')).toBe('http://jobs.example/role')
  })

  it('rejects active, credential-bearing, invalid, and oversized links', () => {
    expect(safeExternalHttpUrl('javascript:alert(1)')).toBeNull()
    expect(safeExternalHttpUrl('data:text/html,unsafe')).toBeNull()
    expect(safeExternalHttpUrl('https://user:pass@jobs.example/role')).toBeNull()
    expect(safeExternalHttpUrl('not a URL')).toBeNull()
    expect(safeExternalHttpUrl(`https://jobs.example/${'x'.repeat(2048)}`)).toBeNull()
  })
})
