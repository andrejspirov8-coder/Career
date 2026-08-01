const API_BASE_URL = process.env.CAREER_API_URL || 'http://127.0.0.1:8000'
const API_TOKEN = process.env.CAREER_DASHBOARD_TOKEN || ''
const SUPABASE_TOKEN_COOKIE_NAME = 'career_sb_token'

export type FastApiBridgeResult<T> = {
  ok: boolean
  data?: T
  error?: string
  schema: string
}

async function getSupabaseToken(): Promise<string | undefined> {
  try {
    const { cookies } = await import('next/headers')
    const cookieStore = await cookies()
    return cookieStore.get(SUPABASE_TOKEN_COOKIE_NAME)?.value
  } catch {
    return undefined
  }
}

async function buildAuthHeaders(): Promise<Record<string, string>> {
  const supabaseToken = await getSupabaseToken()

  const bearerToken = supabaseToken || API_TOKEN

  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${bearerToken}`,
  }
}

async function fetchWithTimeout(
  url: string,
  body: string,
  options: { timeoutMs?: number; errorLabel?: string },
): Promise<Response> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), options.timeoutMs ?? 30_000)
  try {
    const headers = await buildAuthHeaders()
    return await fetch(url, {
      method: 'POST',
      headers,
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
  options: { inputText?: string; timeoutMs?: number; errorLabel?: string } = {},
): Promise<T> {
  const response = await fetchWithTimeout(
    `${API_BASE_URL}/api/v1/helpers/${helper}`,
    JSON.stringify({ args: [...args], input: options.inputText ?? null }),
    options,
  )

  if (!response.ok) {
    const text = await response.text().catch(() => '')
    throw new Error(`${options.errorLabel || 'FastAPI helper'}: ${response.status} ${text}`)
  }

  const result: FastApiBridgeResult<T> = await response.json()
  if (!result.ok) {
    throw new Error(result.error || `${options.errorLabel || 'FastAPI helper'} returned error`)
  }

  return result.data as T
}

export async function runFastApiEndpoint<T>(
  endpoint: string,
  body: unknown,
  options: { timeoutMs?: number; errorLabel?: string } = {},
): Promise<T> {
  const response = await fetchWithTimeout(
    `${API_BASE_URL}/api/v1/${endpoint}`,
    JSON.stringify(body),
    options,
  )
  if (!response.ok) {
    const text = await response.text().catch(() => '')
    throw new Error(`${options.errorLabel || 'FastAPI endpoint'}: ${response.status} ${text}`)
  }
  return (await response.json()) as T
}
