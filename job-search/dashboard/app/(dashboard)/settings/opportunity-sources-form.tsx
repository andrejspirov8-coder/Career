'use client'

import { useState } from 'react'

import type { OpportunityConfig } from '@/lib/opportunity-source-types'

type SourceEntry = [string, { enabled: boolean; [key: string]: unknown }]

function sourceLabel(name: string): string {
  const labels: Record<string, string> = {
    inbox: 'Inbox',
    company_watchlist: 'Company Watchlist',
    official_company_careers: 'Official Company Careers',
    cvmarket_rss: 'CVMarket RSS',
    cvonline_public_search: 'CVOnline',
    cvbankas_public_search: 'CVBankas',
    workinlithuania_public_search: 'Work in Lithuania',
    uzt_open_data: 'UZT Open Data',
    ats: 'ATS Providers',
    linkedin: 'LinkedIn',
    job_board: 'Job Board',
    web_search: 'Web Search',
  }
  return labels[name] || name.replace(/_/g, ' ')
}

export default function OpportunitySourcesForm({ initialConfig }: { initialConfig: OpportunityConfig }) {
  const [config, setConfig] = useState(initialConfig)
  const [status, setStatus] = useState<{ kind: 'idle' | 'saving' | 'ok' | 'error'; message: string }>({
    kind: 'idle',
    message: '',
  })

  const sources = Object.entries(config.opportunities?.sources || {}) as SourceEntry[]

  function toggleSource(name: string) {
    setConfig((current) => {
      const raw = JSON.parse(JSON.stringify(current.opportunities?.sources ?? {}))
      if (raw[name] && typeof raw[name] === 'object') raw[name].enabled = !raw[name].enabled
      return { ...current, opportunities: { ...current.opportunities, sources: raw } } as OpportunityConfig
    })
  }

  async function save() {
    setStatus({ kind: 'saving', message: 'Saving…' })
    try {
      const response = await fetch('/api/opportunity-sources', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'save', sources: config }),
      })
      const payload = (await response.json()) as { ok?: boolean; data?: OpportunityConfig; error?: string }
      if (!response.ok || !payload.ok || !payload.data) {
        throw new Error(payload.error || `HTTP ${response.status}`)
      }
      setConfig(payload.data)
      setStatus({ kind: 'ok', message: 'Sources saved. The next discovery run will use these settings.' })
    } catch (error) {
      setStatus({ kind: 'error', message: error instanceof Error ? error.message : 'Could not save.' })
    }
  }

  return (
    <section className="workspacePanel settingsPanel opportunitySourcesPanel">
      <div className="panelHeading">
        <div>
          <div className="eyebrow">Opportunity sources</div>
          <h2>Where to look</h2>
          <p>Toggle which sources are checked during daily discovery.</p>
        </div>
      </div>

      <div className="sourceGrid">
        {sources.map(([name, source]) => (
          <label key={name} className={`sourceCard ${source.enabled ? 'active' : ''}`}>
            <div className="sourceCardHeader">
              <input
                type="checkbox"
                checked={source.enabled}
                onChange={() => toggleSource(name)}
              />
              <span className="sourceName">{sourceLabel(name)}</span>
              <span className={`sourceBadge ${source.enabled ? 'enabled' : 'disabled'}`}>
                {source.enabled ? 'On' : 'Off'}
              </span>
            </div>
            <div className="sourceCardMeta">{name}</div>
          </label>
        ))}
      </div>

      {status.message ? (
        <div className={`sourceStatus ${status.kind === 'error' ? 'errorText' : status.kind === 'ok' ? 'okText' : 'muted'}`} role="status">
          {status.message}
        </div>
      ) : null}

      <div className="sourceActions">
        <button className="button" type="button" disabled={status.kind === 'saving'} onClick={save}>
          {status.kind === 'saving' ? 'Saving…' : 'Save sources'}
        </button>
      </div>
    </section>
  )
}
