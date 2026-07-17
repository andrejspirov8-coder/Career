import { describe, expect, it } from 'vitest'

import {
  isBackupFilename,
  isBackupPassphrase,
  isRestoreConfirmation,
  isWorkspaceControlAction,
} from './workspace-control'

describe('workspace control validation', () => {
  it('accepts only fixed local actions', () => {
    expect(isWorkspaceControlAction('backup-create')).toBe(true)
    expect(isWorkspaceControlAction('startup-enable')).toBe(true)
    expect(isWorkspaceControlAction('dashboard-restart')).toBe(true)
    expect(isWorkspaceControlAction('run-command')).toBe(false)
    expect(isWorkspaceControlAction('backup-create; rm -rf')).toBe(false)
  })

  it('accepts only generated backup filenames', () => {
    expect(isBackupFilename('career-backup-20260715T120000Z-abcdef.career-backup')).toBe(true)
    expect(isBackupFilename('career-pre-restore-20260715T120000Z-abcdef.career-backup')).toBe(true)
    expect(isBackupFilename('../../dashboard/.env.local')).toBe(false)
    expect(isBackupFilename('career-backup.zip')).toBe(false)
  })

  it('requires a strong in-memory passphrase and exact restore confirmation', () => {
    expect(isBackupPassphrase('correct horse battery staple')).toBe(true)
    expect(isBackupPassphrase('too-short')).toBe(false)
    expect(isRestoreConfirmation('RESTORE')).toBe(true)
    expect(isRestoreConfirmation('restore')).toBe(false)
  })
})
