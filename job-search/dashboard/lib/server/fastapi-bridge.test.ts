import { afterEach, describe, expect, it, vi } from 'vitest'

import { dashboardBackendAuthHeaders, runFastApiEndpoint } from './fastapi-bridge'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('FastAPI bridge authentication', () => {
  it('builds deterministic local bearer headers', () => {
    expect(dashboardBackendAuthHeaders({ CAREER_DASHBOARD_TOKEN: '  secret  ' })).toEqual({
      'Content-Type': 'application/json',
      Authorization: 'Bearer secret',
    })
  })

  it('fails before fetch when the backend token is missing', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    await expect(
      runFastApiEndpoint('health', {}, { env: {} } as never),
    ).rejects.toThrow('CAREER_DASHBOARD_TOKEN is not configured')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('never reads a Supabase cookie for backend authentication', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    )

    await runFastApiEndpoint('health', {}, { env: { CAREER_DASHBOARD_TOKEN: 'secret' } } as never)

    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: {
          'Content-Type': 'application/json',
          Authorization: 'Bearer secret',
        },
      }),
    )
  })
})
