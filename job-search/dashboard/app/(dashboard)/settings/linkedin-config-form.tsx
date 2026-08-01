'use client'

import { useState } from 'react'

import type { LinkedInConfig } from '@/lib/linkedin-config-types'

function variantLabel(key: string): string {
  const labels: Record<string, string> = {
    'luxury-retail': 'Luxury Retail',
    'luxury-retail-lt': 'Luxury Retail (LT)',
    'operations-management': 'Operations Management',
    'operations-management-lt': 'Operations Management (LT)',
    'business-process-operations': 'Business Process Ops',
    'it-business': 'IT Business',
  }
  return labels[key] || key
}

export default function LinkedInConfigForm({ initialConfig }: { initialConfig: LinkedInConfig }) {
  const [config, setConfig] = useState(initialConfig)
  const [status, setStatus] = useState<{ kind: 'idle' | 'saving' | 'ok' | 'error'; message: string }>({
    kind: 'idle',
    message: '',
  })

  function updateNested(path: string[], value: unknown) {
    setConfig((current) => {
      const updated = JSON.parse(JSON.stringify(current)) as Record<string, unknown>
      let target = updated
      for (let i = 0; i < path.length - 1; i++) {
        const segment = target[path[i]]
        if (segment && typeof segment === 'object') target = segment as Record<string, unknown>
        else return current
      }
      target[path[path.length - 1]] = value
      return updated as unknown as LinkedInConfig
    })
  }

  function toggleNested(path: string[]) {
    setConfig((current) => {
      const updated = JSON.parse(JSON.stringify(current)) as Record<string, unknown>
      let target = updated
      for (let i = 0; i < path.length - 1; i++) {
        const segment = target[path[i]]
        if (segment && typeof segment === 'object') target = segment as Record<string, unknown>
        else return current
      }
      target[path[path.length - 1]] = !target[path[path.length - 1]]
      return updated as unknown as LinkedInConfig
    })
  }

  async function save() {
    setStatus({ kind: 'saving', message: 'Saving…' })
    try {
      const response = await fetch('/api/linkedin-config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'save', config }),
      })
      const payload = (await response.json()) as { ok?: boolean; data?: LinkedInConfig; error?: string }
      if (!response.ok || !payload.ok || !payload.data) {
        throw new Error(payload.error || `HTTP ${response.status}`)
      }
      setConfig(payload.data)
      setStatus({ kind: 'ok', message: 'LinkedIn config saved.' })
    } catch (error) {
      setStatus({ kind: 'error', message: error instanceof Error ? error.message : 'Could not save.' })
    }
  }

  const browser = config?.browser
  const limits = config?.limits
  const llm = config?.llm
  const automation = config?.automation
  const search = config?.search
  const notes = config?.connection_notes

  return (
    <section className="workspacePanel settingsPanel linkedinConfigPanel">
      <div className="panelHeading">
        <div>
          <div className="eyebrow">LinkedIn</div>
          <h2>Profile discovery and outreach</h2>
          <p>Browser, search, messaging, and model settings for recruiter workflows.</p>
        </div>
      </div>

      {status.message ? (
        <div className={`sourceStatus ${status.kind === 'error' ? 'errorText' : status.kind === 'ok' ? 'okText' : 'muted'}`} role="status">
          {status.message}
        </div>
      ) : null}

      <div className="linkedinConfigSections">

        {browser ? (
          <details className="linkedinSection" open>
            <summary>Browser</summary>
            <div className="linkedinFields">
              <label>Channel
                <select value={browser.channel} onChange={(e) => updateNested(['browser', 'channel'], e.target.value)}>
                  <option value="chrome">Chrome</option>
                  <option value="chromium">Chromium</option>
                </select>
              </label>
              <label>Backend
                <select value={browser.backend} onChange={(e) => updateNested(['browser', 'backend'], e.target.value)}>
                  <option value="playwright">Playwright</option>
                </select>
              </label>
              <label>Headless
                <input type="checkbox" checked={browser.headless} onChange={() => toggleNested(['browser', 'headless'])} />
              </label>
            </div>
          </details>
        ) : null}

        {limits ? (
          <details className="linkedinSection" open>
            <summary>Limits</summary>
            <div className="linkedinFields">
              <label>Max connections
                <input type="number" min={1} max={100} value={limits.max_connections} onChange={(e) => updateNested(['limits', 'max_connections'], Number(e.target.value))} />
              </label>
              <label>Daily cap
                <input type="number" min={1} max={200} value={limits.daily_cap} onChange={(e) => updateNested(['limits', 'daily_cap'], Number(e.target.value))} />
              </label>
              <label>Min delay (s)
                <input type="number" min={0} max={120} step={1} value={limits.min_delay_seconds} onChange={(e) => updateNested(['limits', 'min_delay_seconds'], Number(e.target.value))} />
              </label>
              <label>Max delay (s)
                <input type="number" min={0} max={300} step={1} value={limits.max_delay_seconds} onChange={(e) => updateNested(['limits', 'max_delay_seconds'], Number(e.target.value))} />
              </label>
            </div>
          </details>
        ) : null}

        {llm ? (
          <details className="linkedinSection">
            <summary>Language model</summary>
            <div className="linkedinFields">
              <label>Provider
                <input type="text" value={llm.provider} onChange={(e) => updateNested(['llm', 'provider'], e.target.value)} />
              </label>
              <label>Model
                <input type="text" value={llm.model} onChange={(e) => updateNested(['llm', 'model'], e.target.value)} />
              </label>
              {llm.profiles ? (
                <div className="linkedinSubSection">
                  <strong>Model profiles</strong>
                  {Object.entries(llm.profiles).map(([name, profile]) => (
                    <div key={name} className="linkedinProfileRow">
                      <span>{name}</span>
                      <span>{profile.provider}/{profile.model}</span>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          </details>
        ) : null}

        {automation ? (
          <details className="linkedinSection">
            <summary>Automation</summary>
            <div className="linkedinFields">
              <label>Max live dispatch
                <input type="number" min={0} max={50} value={automation.max_live_dispatch} onChange={(e) => updateNested(['automation', 'max_live_dispatch'], Number(e.target.value))} />
              </label>
              <label>
                <input type="checkbox" checked={automation.require_llm_note} onChange={() => toggleNested(['automation', 'require_llm_note'])} />
                Require LLM-generated note before dispatch
              </label>
            </div>
          </details>
        ) : null}

        {search?.queries_by_variant ? (
          <details className="linkedinSection">
            <summary>Search queries by CV variant</summary>
            <div className="linkedinFields">
              {Object.entries(search.queries_by_variant).map(([variant, queries]) => (
                <label key={variant}>
                  {variantLabel(variant)}
                  <textarea
                    rows={3}
                    value={(queries as Array<{ keywords: string }>).map((q) => q.keywords).join('\n')}
                    onChange={(e) => {
                      const keywords = e.target.value.split('\n').map((s) => s.trim()).filter(Boolean)
                      updateNested(['search', 'queries_by_variant', variant], keywords.map((k) => ({ keywords: k })))
                    }}
                  />
                </label>
              ))}
            </div>
          </details>
        ) : null}

        {notes ? (
          <details className="linkedinSection">
            <summary>Connection notes by CV variant</summary>
            <div className="linkedinFields">
              {Object.entries(notes).map(([variant, template]) => (
                <label key={variant}>
                  {variantLabel(variant)}
                  <textarea
                    rows={3}
                    value={template}
                    onChange={(e) => updateNested(['connection_notes', variant], e.target.value)}
                  />
                </label>
              ))}
            </div>
          </details>
        ) : null}

      </div>

      <div className="sourceActions">
        <button className="button" type="button" disabled={status.kind === 'saving'} onClick={save}>
          {status.kind === 'saving' ? 'Saving…' : 'Save LinkedIn config'}
        </button>
      </div>
    </section>
  )
}
