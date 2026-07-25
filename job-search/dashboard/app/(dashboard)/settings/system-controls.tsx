'use client'

import { FormEvent, useState } from 'react'

import type { ApiResponse } from '@/lib/api-response'
import type { BackupActionResult, DashboardRestartResult, WorkspaceControlStatus } from '@/lib/workspace-control-types'

function formatDate(value: string) {
  return new Date(value).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })
}

function formatOptionalDate(value: string) {
  return value ? formatDate(value) : 'Unknown'
}

function formatBytes(value: number) {
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`
  return `${(value / (1024 * 1024)).toFixed(1)} MB`
}

export default function SystemControls({ initialStatus }: { initialStatus: WorkspaceControlStatus }) {
  const [status, setStatus] = useState(initialStatus)
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [backupPassphrase, setBackupPassphrase] = useState('')
  const [restorePassphrase, setRestorePassphrase] = useState('')
  const [restoreConfirmation, setRestoreConfirmation] = useState('')
  const [selectedBackup, setSelectedBackup] = useState(initialStatus.backup.backups[0]?.filename || '')

  async function refresh() {
    const response = await fetch('/api/settings/overview', { cache: 'no-store' })
    const payload = (await response.json()) as ApiResponse<WorkspaceControlStatus>
    if (!response.ok || !payload.ok || !payload.data) throw new Error(payload.error || 'Settings could not be refreshed.')
    setStatus(payload.data)
    setSelectedBackup((current) => current || payload.data?.backup.backups[0]?.filename || '')
  }

  async function postAction<T = BackupActionResult>(action: string, input: Record<string, unknown> = {}) {
    const response = await fetch('/api/settings/actions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, ...input }),
    })
    const payload = (await response.json()) as ApiResponse<T>
    if (!response.ok || !payload.ok) throw new Error(payload.error || 'Settings action failed.')
    return payload.data
  }

  async function restartDashboard() {
    setBusy('dashboard-restart')
    setError('')
    setNotice('')
    const previousBuild = status.dashboard.built_at
    try {
      const result = await postAction<DashboardRestartResult>('dashboard-restart')
      setNotice(result?.message || 'The dashboard is rebuilding. This page will reconnect automatically.')
      const deadline = Date.now() + 120_000
      while (Date.now() < deadline) {
        await new Promise((resolvePromise) => window.setTimeout(resolvePromise, 1_500))
        try {
          const response = await fetch('/api/settings/overview', { cache: 'no-store' })
          if (!response.ok) continue
          const payload = (await response.json()) as ApiResponse<WorkspaceControlStatus>
          if (!payload.ok || !payload.data) continue
          if (payload.data.dashboard.last_restart_error) throw new Error(`The rebuild failed: ${payload.data.dashboard.last_restart_error}`)
          if (
            payload.data.dashboard.status === 'current'
            && payload.data.dashboard.built_at
            && payload.data.dashboard.built_at !== previousBuild
          ) {
            window.location.reload()
            return
          }
        } catch (pollError) {
          if (pollError instanceof Error && pollError.message.startsWith('The rebuild failed:')) throw pollError
        }
      }
      throw new Error('The dashboard did not return within two minutes. Run make dashboard-start in the project folder.')
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : 'The dashboard could not be restarted.')
    } finally {
      setBusy('')
    }
  }

  async function changeSimpleControl(action: string, success: string) {
    setBusy(action)
    setError('')
    setNotice('')
    try {
      await postAction(action)
      await refresh()
      setNotice(success)
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : 'Settings action failed.')
    } finally {
      setBusy('')
    }
  }

  async function createBackup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy('backup-create')
    setError('')
    setNotice('')
    try {
      const data = await postAction('backup-create', { passphrase: backupPassphrase })
      setBackupPassphrase('')
      await refresh()
      if (data?.filename) setSelectedBackup(data.filename)
      setNotice(`Encrypted backup created${data?.file_count ? ` with ${data.file_count} files` : ''}. Keep the passphrase separately.`)
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : 'Backup could not be created.')
    } finally {
      setBusy('')
    }
  }

  async function validateOrRestore(action: 'backup-validate' | 'backup-restore') {
    setBusy(action)
    setError('')
    setNotice('')
    try {
      const data = await postAction(action, {
        filename: selectedBackup,
        passphrase: restorePassphrase,
        confirmation: action === 'backup-restore' ? restoreConfirmation : undefined,
      })
      setRestorePassphrase('')
      if (action === 'backup-restore') setRestoreConfirmation('')
      await refresh()
      setNotice(action === 'backup-validate'
        ? `Backup verified${data?.file_count ? `: ${data.file_count} files are intact` : ''}.`
        : `Private data restored safely. A pre-restore backup was created as ${data?.safety_backup || 'a safety copy'}.`)
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : 'Backup action failed.')
    } finally {
      setBusy('')
    }
  }

  return (
    <>
      {error ? <div className="banner settingsWideMessage" role="alert">{error}</div> : null}
      {notice ? <div className="noticeBanner settingsWideMessage" role="status">{notice}</div> : null}

      <section className={`workspacePanel settingsPanel buildStatusPanel ${status.dashboard.update_available ? 'needsUpdate' : ''}`}>
        <div className="panelHeading">
          <div>
            <div className="eyebrow">App version</div>
            <h2>{status.dashboard.status === 'update_available' ? 'A newer local build is needed' : status.dashboard.status === 'current' ? 'Dashboard is current' : 'Build status unavailable'}</h2>
            <p>{status.dashboard.update_available ? 'The files on this Mac changed after the running dashboard was built.' : 'The running dashboard matches the current local files.'}</p>
          </div>
          <span className={`buildStatusFlag ${status.dashboard.status}`}>{status.dashboard.status === 'update_available' ? 'Update needed' : status.dashboard.status === 'current' ? 'Current' : 'Unknown'}</span>
        </div>
        <div className="settingsRows">
          <div><span>Running build</span><strong>{formatOptionalDate(status.dashboard.built_at)}</strong><small>Embedded when the production dashboard was built.</small></div>
          <div><span>Latest app file</span><strong>{formatOptionalDate(status.dashboard.latest_source_modified_at)}</strong><small>Only dashboard code and package files are checked.</small></div>
          <div><span>Managed restart</span><strong>{status.dashboard.restart_supported ? 'Ready' : 'Manual'}</strong><small>{status.dashboard.restart_supported ? 'The local supervisor can rebuild and reconnect this page.' : 'Use the production launcher to enable one-click restart.'}</small></div>
        </div>
        {status.dashboard.last_restart_error ? <p className="errorText small">Last rebuild failed: {status.dashboard.last_restart_error}</p> : null}
        {status.dashboard.update_available && status.dashboard.restart_supported ? (
          <button className="button" disabled={Boolean(busy)} onClick={restartDashboard} type="button">{busy === 'dashboard-restart' ? 'Rebuilding and reconnecting…' : 'Rebuild and restart safely'}</button>
        ) : status.dashboard.update_available ? (
          <div className="startupCommand"><code>make dashboard-start</code></div>
        ) : <p className="muted small">No restart is needed.</p>}
      </section>

      <section className="workspacePanel settingsPanel">
        <div className="panelHeading">
          <div><div className="eyebrow">Login secret</div><h2>Secure local storage</h2><p>Use macOS Keychain instead of a project settings file.</p></div>
        </div>
        <div className="settingsRows">
          <div><span>Current storage</span><strong>{status.keychain.storage === 'keychain' ? 'macOS Keychain' : status.keychain.storage === 'environment' ? 'Current server process' : status.keychain.configured ? 'Private settings file' : 'Not configured'}</strong><small>The secret itself is never shown here.</small></div>
          <div><span>Browser login</span><strong>Remembered</strong><small>The private cookie survives normal restarts.</small></div>
        </div>
        {status.keychain.supported ? (
          status.keychain.storage === 'keychain' ? (
            <button className="button secondary" disabled={Boolean(busy)} onClick={() => changeSimpleControl('keychain-disable', 'The login secret is back in the private local settings file.')} type="button">Use private settings file</button>
          ) : (
            <button className="button" disabled={Boolean(busy)} onClick={() => changeSimpleControl('keychain-enable', 'The login secret is now protected by macOS Keychain.')} type="button">Move secret to Keychain</button>
          )
        ) : <p className="muted small">Keychain controls are available on macOS.</p>}
      </section>

      <section className="workspacePanel settingsPanel backupPanel">
        <div className="panelHeading">
          <div><div className="eyebrow">Recovery</div><h2>Encrypted workspace backup</h2><p>Protect private job data, CVs, packs, preferences, and application notes.</p></div>
        </div>
        <form className="secureActionForm" onSubmit={createBackup}>
          <label>
            New backup passphrase
            <input autoComplete="new-password" minLength={12} onChange={(event) => setBackupPassphrase(event.target.value)} required type="password" value={backupPassphrase} />
          </label>
          <button className="button" disabled={Boolean(busy)} type="submit">{busy === 'backup-create' ? 'Encrypting…' : 'Create encrypted backup'}</button>
          <small>Use at least 12 characters. The passphrase is not saved, so keep it in your password manager.</small>
        </form>
        <div className="backupList">
          {status.backup.backups.length ? status.backup.backups.slice(0, 4).map((backup) => (
            <div key={backup.filename}>
              <span><strong>{backup.pre_restore ? 'Safety backup' : 'Workspace backup'}</strong><small>{formatDate(backup.created_at)} · {formatBytes(backup.size_bytes)}</small></span>
              <a href={`/api/settings/backups/${encodeURIComponent(backup.filename)}`}>Download</a>
            </div>
          )) : <p className="muted small">No encrypted backups yet.</p>}
        </div>
        {status.backup.backups.length ? (
          <details className="restoreDetails">
            <summary>Verify or restore a backup</summary>
            <label>Backup<select onChange={(event) => setSelectedBackup(event.target.value)} value={selectedBackup}>{status.backup.backups.map((backup) => <option key={backup.filename} value={backup.filename}>{formatDate(backup.created_at)}{backup.pre_restore ? ' — safety' : ''}</option>)}</select></label>
            <label>Passphrase<input autoComplete="current-password" minLength={12} onChange={(event) => setRestorePassphrase(event.target.value)} type="password" value={restorePassphrase} /></label>
            <div className="buttonRow"><button className="button secondary" disabled={Boolean(busy) || restorePassphrase.length < 12} onClick={() => validateOrRestore('backup-validate')} type="button">Verify integrity</button></div>
            <label>To restore, type RESTORE<input autoComplete="off" disabled={!status.backup.restore_available} onChange={(event) => setRestoreConfirmation(event.target.value)} value={restoreConfirmation} /></label>
            <button className="button dangerButton" disabled={Boolean(busy) || !status.backup.restore_available || restorePassphrase.length < 12 || restoreConfirmation !== 'RESTORE'} onClick={() => validateOrRestore('backup-restore')} type="button">Restore private data</button>
            {!status.backup.restore_available ? (
              <>
                <small>Restore is locked while the automation worker is online. Verification still works here.</small>
                <div className="startupCommand"><code>make dashboard-restore BACKUP={selectedBackup || 'backup-file'}</code></div>
                <small>Stop the service, run this command, and enter the passphrase when asked.</small>
              </>
            ) : <small>Restore overlays verified files and creates an encrypted safety backup first.</small>}
          </details>
        ) : null}
      </section>

      <section className="workspacePanel settingsPanel">
        <div className="panelHeading">
          <div><div className="eyebrow">Startup</div><h2>Open after macOS sign-in</h2><p>Install a private local startup file for the next sign-in.</p></div>
        </div>
        <div className="settingsRows">
          <div><span>Automatic startup</span><strong>{status.startup.installed ? 'Enabled' : 'Off'}</strong><small>{status.startup.loaded ? 'The startup service is currently loaded.' : status.startup.installed ? 'It will load at the next macOS sign-in.' : 'The app starts only when you ask.'}</small></div>
          <div><span>Network</span><strong>127.0.0.1 only</strong><small>Startup does not make the dashboard public.</small></div>
        </div>
        {status.startup.supported ? (
          status.startup.installed ? (
            <button className="button secondary" disabled={Boolean(busy)} onClick={() => changeSimpleControl('startup-disable', 'Automatic startup is disabled.')} type="button">Disable automatic startup</button>
          ) : (
            <button className="button" disabled={Boolean(busy)} onClick={() => changeSimpleControl('startup-enable', 'Automatic startup is ready for the next macOS sign-in.')} type="button">Enable for next sign-in</button>
          )
        ) : <p className="muted small">Automatic sign-in startup is available on macOS.</p>}
        <div className="startupCommand"><code>make dashboard-start</code></div>
      </section>
    </>
  )
}
