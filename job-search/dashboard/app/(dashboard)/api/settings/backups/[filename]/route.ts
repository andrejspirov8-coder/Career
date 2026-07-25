import { readFile } from 'node:fs/promises'

import { applyDashboardPrivateHeaders, dashboardAuthErrorResponse, dashboardJsonResponse } from '@/lib/server/auth'
import { resolveWorkspaceBackup } from '@/lib/workspace-control'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(
  request: Request,
  { params }: { params: Promise<{ filename: string }> },
) {
  const authError = dashboardAuthErrorResponse(request)
  if (authError) return authError
  const { filename } = await params
  const file = await resolveWorkspaceBackup(filename)
  if (!file) return dashboardJsonResponse({ ok: false, error: 'Backup file was not found.' }, { status: 404 })
  try {
    const data = await readFile(file.path)
    const body = data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength) as ArrayBuffer
    return applyDashboardPrivateHeaders(new Response(body, {
      headers: {
        'Content-Disposition': `attachment; filename="${file.filename}"`,
        'Content-Length': String(file.size),
        'Content-Type': 'application/octet-stream',
      },
    }))
  } catch {
    return dashboardJsonResponse({ ok: false, error: 'Backup file could not be read.' }, { status: 404 })
  }
}
