import { describe, expect, it } from 'vitest'

import { isLocalDraftType, isLocalModelName } from './local-drafting'

describe('local drafting validation', () => {
  it('allows only reviewable draft types', () => {
    expect(isLocalDraftType('cover_letter')).toBe(true)
    expect(isLocalDraftType('follow_up')).toBe(true)
    expect(isLocalDraftType('auto_apply')).toBe(false)
    expect(isLocalDraftType('send_message')).toBe(false)
  })

  it('accepts model names but rejects remote URLs and shell fragments', () => {
    expect(isLocalModelName('qwen3.5:35b-a3b-fast')).toBe(true)
    expect(isLocalModelName('http://remote.example/model')).toBe(false)
    expect(isLocalModelName('model; curl example.com')).toBe(false)
  })
})
