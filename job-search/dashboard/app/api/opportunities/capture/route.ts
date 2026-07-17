import { dashboardJsonResponse, dashboardMutationAuthErrorResponse } from '../../../../lib/server/auth'
import { captureOpportunity, type OpportunityCaptureInput } from '../../../../lib/opportunity-data'
import { safeExternalHttpUrl } from '../../../../lib/safe-url'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

function boundedText(value: unknown, name: string, maxLength: number): string {
  if (value === undefined || value === null) return ''
  if (typeof value !== 'string' || value.length > maxLength) {
    throw new Error(`${name} must be ${maxLength.toLocaleString()} characters or fewer.`)
  }
  return value.trim()
}

export async function POST(request: Request) {
  const authError = dashboardMutationAuthErrorResponse(request)
  if (authError) return authError

  try {
    const body = (await request.json()) as Record<string, unknown>
    const unknown = Object.keys(body).filter((key) => !['url', 'text', 'title', 'company', 'location'].includes(key))
    if (unknown.length) {
      return dashboardJsonResponse({ ok: false, error: `Unsupported capture field: ${unknown[0]}.` }, { status: 400 })
    }

    const rawUrl = boundedText(body.url, 'Job URL', 2048)
    const url = rawUrl ? safeExternalHttpUrl(rawUrl) : ''
    if (rawUrl && !url) {
      return dashboardJsonResponse({ ok: false, error: 'Job URL must be a normal HTTP or HTTPS link.' }, { status: 400 })
    }
    const input: OpportunityCaptureInput = {
      url: url || '',
      text: boundedText(body.text, 'Job text', 50_000),
      title: boundedText(body.title, 'Title', 200),
      company: boundedText(body.company, 'Company', 200),
      location: boundedText(body.location, 'Location', 200),
    }
    if (!input.url && !input.text) {
      return dashboardJsonResponse({ ok: false, error: 'Paste a job URL or some job text.' }, { status: 400 })
    }
    return dashboardJsonResponse({ ok: true, data: await captureOpportunity(input) }, { status: 201 })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Opportunity capture failed.'
    const status = error instanceof SyntaxError ? 400 : 422
    return dashboardJsonResponse({ ok: false, error: message }, { status })
  }
}
