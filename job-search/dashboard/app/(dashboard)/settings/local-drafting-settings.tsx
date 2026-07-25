'use client'

import { FormEvent, useState } from 'react'

import type { ApiResponse } from '@/lib/api-response'
import type { LocalDraftingStatus } from '@/lib/local-drafting-types'

export default function LocalDraftingSettings({ initialStatus }: { initialStatus: LocalDraftingStatus }) {
  const [status, setStatus] = useState(initialStatus)
  const [enabled, setEnabled] = useState(initialStatus.enabled)
  const [model, setModel] = useState(initialStatus.model)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setNotice('')
    setError('')
    try {
      const response = await fetch('/api/ai/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled, model }),
      })
      const payload = (await response.json()) as ApiResponse<LocalDraftingStatus>
      if (!response.ok || !payload.ok || !payload.data) throw new Error(payload.error || 'Local drafting settings could not be saved.')
      setStatus(payload.data)
      setEnabled(payload.data.enabled)
      setModel(payload.data.model)
      setNotice(payload.data.enabled ? 'Local drafting is enabled. Drafts still require a click and review.' : 'Local drafting is off.')
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : 'Local drafting settings could not be saved.')
    } finally {
      setBusy(false)
    }
  }

  const installedModels = status.ollama.models
  const selectableModels = installedModels.includes(model) ? installedModels : [model, ...installedModels]

  return (
    <section className="workspacePanel settingsPanel localAiPanel">
      <div className="panelHeading">
        <div><div className="eyebrow">Optional assistance</div><h2>Local drafting</h2><p>Draft cover letters and follow-ups with Ollama running only on this Mac.</p></div>
        <span className={`statusPill ${status.ollama.online ? 'status-succeeded' : 'status-partial'}`}>{status.ollama.online ? 'Local model online' : 'Local model offline'}</span>
      </div>
      {error ? <div className="banner section" role="alert">{error}</div> : null}
      {notice ? <div className="noticeBanner section" role="status">{notice}</div> : null}
      <div className="privacyFacts">
        <div><span>Network</span><strong>127.0.0.1 only</strong></div>
        <div><span>Automatic actions</span><strong>None</strong></div>
        <div><span>Dashboard prompt storage</span><strong>Off</strong></div>
      </div>
      <form className="localAiForm" onSubmit={save}>
        <label className="toggleLabel">
          <input checked={enabled} onChange={(event) => setEnabled(event.target.checked)} type="checkbox" />
          <span>Enable local drafting in Applications</span>
        </label>
        <label>
          Local model
          <select disabled={!installedModels.length} onChange={(event) => setModel(event.target.value)} value={model}>
            {selectableModels.map((item) => <option key={item} value={item}>{item}{installedModels.includes(item) ? '' : ' — not installed'}</option>)}
          </select>
        </label>
        <button className="button" disabled={busy || (enabled && (!status.ollama.online || !installedModels.includes(model)))} type="submit">{busy ? 'Saving…' : 'Save local drafting setting'}</button>
      </form>
      <p className="muted small">{status.ollama.message} The dashboard does not save prompts, but your separate Ollama installation controls its own logs. Enabling this does not enable cloud AI, automatic applications, or automatic LinkedIn sending.</p>
    </section>
  )
}
