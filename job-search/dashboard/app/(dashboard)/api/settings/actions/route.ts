import { dashboardJsonResponse, dashboardMutationAuthErrorResponse } from '@/lib/server/auth'
import {
  isBackupFilename,
  isBackupPassphrase,
  isRestoreConfirmation,
  isWorkspaceControlAction,
  runWorkspaceControlAction,
} from '@/lib/workspace-control'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

type SettingsActionBody = {
  action?: unknown
  passphrase?: unknown
  filename?: unknown
  confirmation?: unknown
}

export async function POST(request: Request) {
  const authError = dashboardMutationAuthErrorResponse(request)
  if (authError) return authError
  let body: SettingsActionBody
  try {
    body = (await request.json()) as SettingsActionBody
  } catch {
    return dashboardJsonResponse({ ok: false, error: 'Invalid settings request.' }, { status: 400 })
  }
  if (!isWorkspaceControlAction(body.action)) {
    return dashboardJsonResponse({ ok: false, error: 'Unsupported settings action.' }, { status: 400 })
  }
  if (body.action.startsWith('backup-') && !isBackupPassphrase(body.passphrase)) {
    return dashboardJsonResponse(
      { ok: false, error: 'The backup passphrase must be at least 12 characters.' },
      { status: 400 },
    )
  }
  if (
    (body.action === 'backup-validate' || body.action === 'backup-restore') &&
    !isBackupFilename(body.filename)
  ) {
    return dashboardJsonResponse({ ok: false, error: 'Choose a valid Career backup file.' }, { status: 400 })
  }
  if (body.action === 'backup-restore' && !isRestoreConfirmation(body.confirmation)) {
    return dashboardJsonResponse({ ok: false, error: 'Type RESTORE exactly to confirm recovery.' }, { status: 400 })
  }
  try {
    const data = await runWorkspaceControlAction(body.action, {
      passphrase: typeof body.passphrase === 'string' ? body.passphrase : undefined,
      filename: typeof body.filename === 'string' ? body.filename : undefined,
      confirmation: typeof body.confirmation === 'string' ? body.confirmation : undefined,
    })
    return dashboardJsonResponse({ ok: true, data })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Workspace control failed.'
    return dashboardJsonResponse({ ok: false, error: message }, { status: 409 })
  }
}
