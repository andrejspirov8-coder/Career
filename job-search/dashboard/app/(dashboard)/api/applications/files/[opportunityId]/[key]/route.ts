import { readFile } from 'node:fs/promises'

import { resolveApplicationPackFile } from '@/lib/application-data'
import { dashboardAuthErrorResponse, dashboardJsonResponse } from '@/lib/server/auth'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(
  request: Request,
  { params }: { params: Promise<{ opportunityId: string; key: string }> },
) {
  const authError = dashboardAuthErrorResponse(request)
  if (authError) return authError
  const { opportunityId, key } = await params
  const file = await resolveApplicationPackFile(opportunityId, key)
  if (!file) return dashboardJsonResponse({ ok: false, error: 'Application file was not found.' }, { status: 404 })
  try {
    const data = await readFile(file.path)
    const body = data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength) as ArrayBuffer
    return new Response(body, {
      headers: {
        'Cache-Control': 'no-store, max-age=0',
        'Content-Disposition': `attachment; filename="${file.filename.replace(/["\\]/g, '_')}"`,
        'Content-Length': String(data.byteLength),
        'Content-Type': file.filename.endsWith('.json') ? 'application/json' : 'text/plain; charset=utf-8',
        Pragma: 'no-cache',
        'X-Content-Type-Options': 'nosniff',
      },
    })
  } catch {
    return dashboardJsonResponse({ ok: false, error: 'Application file could not be read.' }, { status: 404 })
  }
}
