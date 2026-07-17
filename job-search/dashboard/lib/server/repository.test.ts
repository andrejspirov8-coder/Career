import { describe, expect, it } from 'vitest'

import { resolveRepositoryRoot } from './repository'

describe('repository root resolution', () => {
  it('uses an explicit configured root first', () => {
    expect(resolveRepositoryRoot('/tmp/project/dashboard', '/tmp/managed-career'))
      .toBe('/tmp/managed-career')
  })

  it('resolves from the dashboard folder without platform-specific separators', () => {
    expect(resolveRepositoryRoot('/tmp/project/dashboard', ''))
      .toBe('/tmp/project')
  })

  it('keeps an already resolved repository root', () => {
    expect(resolveRepositoryRoot('/tmp/project', ''))
      .toBe('/tmp/project')
  })
})
