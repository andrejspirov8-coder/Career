'use client'

import { useState } from 'react'

import type { RuntimeSettings } from '@/lib/runtime-settings-types'

export default function RuntimeSettingsForm({ initialSettings }: { initialSettings: RuntimeSettings }) {
  const [settings, setSettings] = useState(initialSettings)
  const [status, setStatus] = useState<{ kind: 'idle' | 'saving' | 'ok' | 'error'; message: string }>({
    kind: 'idle',
    message: '',
  })

  function update(path: string[], value: unknown) {
    setSettings((current) => {
      const raw = JSON.parse(JSON.stringify(current)) as Record<string, unknown>
      let target = raw
      for (let i = 0; i < path.length - 1; i++) {
        target = target[path[i]] as Record<string, unknown>
      }
      target[path[path.length - 1]] = value
      return raw as unknown as RuntimeSettings
    })
  }

  function toggle(path: string[]) {
    setSettings((current) => {
      const raw = JSON.parse(JSON.stringify(current)) as Record<string, unknown>
      let target = raw
      for (let i = 0; i < path.length - 1; i++) {
        target = target[path[i]] as Record<string, unknown>
      }
      target[path[path.length - 1]] = !target[path[path.length - 1]]
      return raw as unknown as RuntimeSettings
    })
  }

  async function save() {
    setStatus({ kind: 'saving', message: 'Saving…' })
    try {
      const response = await fetch('/api/runtime-settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'save', settings }),
      })
      const payload = (await response.json()) as { ok?: boolean; data?: RuntimeSettings; error?: string }
      if (!response.ok || !payload.ok || !payload.data) {
        throw new Error(payload.error || `HTTP ${response.status}`)
      }
      setSettings(payload.data)
      setStatus({ kind: 'ok', message: 'Runtime settings saved.' })
    } catch (error) {
      setStatus({ kind: 'error', message: error instanceof Error ? error.message : 'Could not save.' })
    }
  }

  const rt = settings?.runtime
  const limits = settings?.limits

  return (
    <section className="workspacePanel settingsPanel runtimeSettingsPanel">
      <div className="panelHeading">
        <div>
          <div className="eyebrow">Runtime</div>
          <h2>Recruiter workflow settings</h2>
          <p>Safety controls, dispatch limits, and automation behavior.</p>
        </div>
      </div>

      {status.message ? (
        <div className={`sourceStatus ${status.kind === 'error' ? 'errorText' : status.kind === 'ok' ? 'okText' : 'muted'}`} role="status">
          {status.message}
        </div>
      ) : null}

      <div className="runtimeFields">
        {rt ? (
          <>
            <label>Mode
              <select value={rt.mode} onChange={(e) => update(['runtime', 'mode'], e.target.value)}>
                <option value="review_first">Review first</option>
                <option value="automatic">Automatic</option>
                <option value="dry_run">Dry run only</option>
              </select>
            </label>
            <label className="checkboxLabel">
              <input type="checkbox" checked={rt.dry_run_default} onChange={() => toggle(['runtime', 'dry_run_default'])} />
              Dry run by default
            </label>
            <label className="checkboxLabel">
              <input type="checkbox" checked={rt.require_live_dispatch_ack} onChange={() => toggle(['runtime', 'require_live_dispatch_ack'])} />
              Require live dispatch acknowledgment
            </label>
            <label className="checkboxLabel">
              <input type="checkbox" checked={rt.require_approval_ledger} onChange={() => toggle(['runtime', 'require_approval_ledger'])} />
              Require approval ledger
            </label>
          </>
        ) : null}

        {limits ? (
          <>
            <label>Max live dispatch batch
              <input type="number" min={1} max={10} value={limits.max_live_dispatch_batch} onChange={(e) => update(['limits', 'max_live_dispatch_batch'], Number(e.target.value))} />
            </label>
            <label className="checkboxLabel">
              <input type="checkbox" checked={limits.stop_on_captcha} onChange={() => toggle(['limits', 'stop_on_captcha'])} />
              Stop on CAPTCHA
            </label>
            <label className="checkboxLabel">
              <input type="checkbox" checked={limits.stop_on_checkpoint} onChange={() => toggle(['limits', 'stop_on_checkpoint'])} />
              Stop on checkpoint
            </label>
            <label className="checkboxLabel">
              <input type="checkbox" checked={limits.stop_on_unusual_activity} onChange={() => toggle(['limits', 'stop_on_unusual_activity'])} />
              Stop on unusual activity
            </label>
          </>
        ) : null}
      </div>

      <div className="sourceActions">
        <button className="button" type="button" disabled={status.kind === 'saving'} onClick={save}>
          {status.kind === 'saving' ? 'Saving…' : 'Save runtime settings'}
        </button>
      </div>
    </section>
  )
}
