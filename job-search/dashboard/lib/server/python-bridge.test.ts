import { describe, expect, it } from 'vitest'

import { parsePythonHelperEnvelope } from './python-bridge'

describe('shared Python bridge envelopes', () => {
  it('parses JSON from stdout when warnings are present on stderr', () => {
    expect(parsePythonHelperEnvelope<{ count: number }>({
      stdout: JSON.stringify({ schema: 'career_python_helper_v1', ok: true, data: { count: 3 } }),
      stderr: 'warning: local cache is stale',
      exitCode: 0,
    })).toEqual({ count: 3 })
  })

  it('rejects invalid JSON consistently', () => {
    expect(() => parsePythonHelperEnvelope({ stdout: 'not-json', stderr: '', exitCode: 0 }, 'Test helper'))
      .toThrow('Test helper returned invalid JSON.')
  })

  it('includes both process streams in a non-zero failure', () => {
    expect(() => parsePythonHelperEnvelope({ stdout: 'bad stdout', stderr: 'bad stderr', exitCode: 2 }, 'Test helper'))
      .toThrow(/stderr: bad stderr.*stdout: bad stdout/)
  })

  it('rejects unknown versioned envelopes', () => {
    expect(() => parsePythonHelperEnvelope({
      stdout: JSON.stringify({ schema: 'career_python_helper_v2', ok: true, data: {} }),
      stderr: '',
      exitCode: 0,
    }, 'Test helper')).toThrow('unsupported response version')
  })

  it('rejects unversioned JSON responses', () => {
    expect(() => parsePythonHelperEnvelope({
      stdout: JSON.stringify({ ok: true, data: {} }),
      stderr: '',
      exitCode: 0,
    }, 'Test helper')).toThrow('unsupported response version')
  })
})
