import { readFile } from 'node:fs/promises'

import { dashboardAuthErrorResponse, dashboardJsonResponse } from '../../../../../lib/server/auth'
import { isCvFormat, resolveCvPdf } from '../../../../../lib/cv-data'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(
  request: Request,
  { params }: { params: Promise<{ variant: string; format: string }> },
) {
  const authError = dashboardAuthErrorResponse(request)
  if (authError) return authError

  const { variant, format } = await params
  if (!isCvFormat(format)) {
    return dashboardJsonResponse({ ok: false, error: 'Unknown CV format.' }, { status: 400 })
  }
  const file = await resolveCvPdf(variant, format)
  if (!file) {
    return dashboardJsonResponse({ ok: false, error: 'CV variant was not found.' }, { status: 404 })
  }

  try {
    const data = await readFile(file.path)
    const body = data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength) as ArrayBuffer
    const disposition = new URL(request.url).searchParams.get('download') === '1' ? 'attachment' : 'inline'
    return new Response(body, {
      headers: {
        'Cache-Control': 'no-store, max-age=0',
        'Content-Disposition': `${disposition}; filename="${file.filename}"`,
        'Content-Length': String(data.byteLength),
        'Content-Type': 'application/pdf',
        Pragma: 'no-cache',
        'X-Content-Type-Options': 'nosniff',
      },
    })
  } catch {
    return dashboardJsonResponse(
      { ok: false, error: 'This CV has not been generated yet.' },
      { status: 404 },
    )
  }
}
