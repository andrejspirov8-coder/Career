const API_BASE_URL = process.env.CAREER_API_URL || 'http://127.0.0.1:8000'

import type { PythonHelperEnvelopeV1 as GeneratedPythonHelperEnvelopeV1 } from '@/lib/generated/envelope'

export type FastApiBridgeResult<T> = GeneratedPythonHelperEnvelopeV1 & {
  data?: T
}

type BridgeOptions = {
  inputText?: string
  timeoutMs?: number
  errorLabel?: string
  env?: NodeJS.ProcessEnv
}

export function dashboardBackendAuthHeaders(
  env: NodeJS.ProcessEnv = process.env,
): Record<string, string> {
  const token = (env.CAREER_DASHBOARD_TOKEN || '').trim()
  if (!token) throw new Error('CAREER_DASHBOARD_TOKEN is not configured')
  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${token}`,
  }
}

async function fetchWithTimeout(
  url: string,
  body: string,
  options: BridgeOptions,
): Promise<Response> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), options.timeoutMs ?? 30_000)
  try {
    return await fetch(url, {
      method: 'POST',
      headers: dashboardBackendAuthHeaders(options.env),
      body,
      signal: controller.signal,
    })
  } finally {
    clearTimeout(timeout)
  }
}

export async function runFastApiHelper<T>(
  helper: string,
  args: readonly string[] = [],
  options: BridgeOptions = {},
): Promise<T> {
  const response = await fetchWithTimeout(
    `${API_BASE_URL}/api/v1/helpers/${helper}`,
    JSON.stringify({ args: [...args], input: options.inputText ?? null }),
    options,
  )
  if (!response.ok) {
    throw new Error(`${options.errorLabel || 'FastAPI helper'}: ${response.status} ${await response.text().catch(() => '')}`)
  }
  const result: FastApiBridgeResult<T> = await response.json()
  if (!result.ok) throw new Error(result.error || `${options.errorLabel || 'FastAPI helper'} returned error`)
  return result.data as T
}

export async function runFastApiEndpoint<T>(
  endpoint: string,
  body: unknown,
  options: BridgeOptions = {},
): Promise<T> {
  const response = await fetchWithTimeout(
    `${API_BASE_URL}/api/v1/${endpoint}`,
    JSON.stringify(body),
    options,
  )
  if (!response.ok) {
    throw new Error(`${options.errorLabel || 'FastAPI endpoint'}: ${response.status} ${await response.text().catch(() => '')}`)
  }
  return (await response.json()) as T
}
