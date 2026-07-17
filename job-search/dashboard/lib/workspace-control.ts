import { realpath, stat } from 'node:fs/promises'
import { join, resolve, sep } from 'node:path'

import type {
  BackupActionResult,
  DashboardRuntimeStatus,
  DashboardRestartResult,
  WorkspaceControlAction,
  WorkspaceControlStatus,
} from './workspace-control-types'
import { getDashboardBuildStatus } from './build-status'
import { runPythonHelper } from './server/python-bridge'
import { repositoryRoot } from './server/repository'

const backupRoot = resolve(repositoryRoot, 'state', 'backups')
const helperTimeoutMs = 180_000
const maxOutputBytes = 2 * 1024 * 1024
const maxBackupBytes = 301 * 1024 * 1024
const backupFilenamePattern = /^career-(?:backup|pre-restore)-\d{8}T\d{6}Z(?:-[a-f0-9]{6})?\.career-backup$/
const actions = new Set<WorkspaceControlAction>([
  'dashboard-restart',
  'keychain-enable',
  'keychain-disable',
  'startup-enable',
  'startup-disable',
  'backup-create',
  'backup-validate',
  'backup-restore',
])

export function isWorkspaceControlAction(value: unknown): value is WorkspaceControlAction {
  return typeof value === 'string' && actions.has(value as WorkspaceControlAction)
}

export function isBackupFilename(value: unknown): value is string {
  return typeof value === 'string' && backupFilenamePattern.test(value)
}

export function isBackupPassphrase(value: unknown): value is string {
  return typeof value === 'string' && value.length >= 12 && value.length <= 256
}

export function isRestoreConfirmation(value: unknown): value is 'RESTORE' {
  return value === 'RESTORE'
}

function executeHelper<T>(command: string, input?: Record<string, unknown>): Promise<T> {
  return runPythonHelper<T>('workspace', [command], {
    input,
    timeoutMs: helperTimeoutMs,
    maxOutputBytes,
    errorLabel: 'The local workspace control',
  })
}

export async function getWorkspaceControlStatus(): Promise<WorkspaceControlStatus> {
  type RawWorkspaceControlStatus = Omit<WorkspaceControlStatus, 'dashboard'> & {
    dashboard_runtime: DashboardRuntimeStatus
  }
  const controls = await executeHelper<RawWorkspaceControlStatus>('status')
  const { dashboard_runtime: runtime, ...workspace } = controls
  return { ...workspace, dashboard: getDashboardBuildStatus(runtime) }
}

export async function runWorkspaceControlAction(
  action: WorkspaceControlAction,
  input: { passphrase?: string; filename?: string; confirmation?: string } = {},
): Promise<unknown | BackupActionResult | DashboardRestartResult> {
  if (!isWorkspaceControlAction(action)) throw new Error('Unsupported workspace control.')
  const requiresPassphrase = action.startsWith('backup-')
  if (requiresPassphrase && !isBackupPassphrase(input.passphrase)) {
    throw new Error('The backup passphrase must be at least 12 characters.')
  }
  if ((action === 'backup-validate' || action === 'backup-restore') && !isBackupFilename(input.filename)) {
    throw new Error('Choose a valid Career backup file.')
  }
  if (action === 'backup-restore' && !isRestoreConfirmation(input.confirmation)) {
    throw new Error('Type RESTORE exactly to confirm recovery.')
  }
  return executeHelper(action, input)
}

export async function resolveWorkspaceBackup(filename: string) {
  if (!isBackupFilename(filename)) return null
  try {
    const root = await realpath(backupRoot)
    const path = await realpath(join(backupRoot, filename))
    const details = await stat(path)
    if (!path.startsWith(`${root}${sep}`) || !details.isFile() || details.size > maxBackupBytes) return null
    return { path, filename, size: details.size }
  } catch {
    return null
  }
}
