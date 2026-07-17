import { describe, expect, it } from 'vitest'

import { isCvStudioContent, isCvStudioVersionId } from './cv-studio'

describe('CV Studio validation', () => {
  it('accepts only fixed generated version identifiers', () => {
    expect(isCvStudioVersionId('20260715T020000Z-abcdef123456')).toBe(true)
    expect(isCvStudioVersionId('../../cv/source')).toBe(false)
    expect(isCvStudioVersionId('2026-07-15')).toBe(false)
  })

  it('bounds source content before a helper process starts', () => {
    expect(isCvStudioContent('# Andrej')).toBe(true)
    expect(isCvStudioContent('')).toBe(false)
    expect(isCvStudioContent('x'.repeat(100_001))).toBe(false)
  })
})
