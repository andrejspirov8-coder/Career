'use client'

import { useState } from 'react'

import {
  type SearchPreferences,
  type WorkArrangement,
  workArrangementValues,
} from '@/lib/search-preference-types'

const arrangementLabels: Record<WorkArrangement, string> = {
  on_site: 'On-site in Vilnius',
  hybrid: 'Hybrid',
  remote_lithuania: 'Remote in Lithuania',
  remote_eu: 'Remote in the EU',
}

function listText(values: string[]) {
  return values.join('\n')
}

function parseList(value: string) {
  return value
    .split(/\n|,/)
    .map((item) => item.trim())
    .filter(Boolean)
}

export default function SearchProfileForm({ initialPreferences }: { initialPreferences: SearchPreferences }) {
  const [preferences, setPreferences] = useState(initialPreferences)
  const [targetRoles, setTargetRoles] = useState(listText(initialPreferences.target_roles))
  const [locations, setLocations] = useState(listText(initialPreferences.priority_locations))
  const [excludedKeywords, setExcludedKeywords] = useState(listText(initialPreferences.excluded_keywords))
  const [excludedCompanies, setExcludedCompanies] = useState(listText(initialPreferences.excluded_companies))
  const [status, setStatus] = useState<{ kind: 'idle' | 'saving' | 'ok' | 'error'; message: string }>({
    kind: 'idle',
    message: '',
  })

  function toggleArrangement(value: WorkArrangement) {
    setPreferences((current) => {
      const selected = current.work_arrangements.includes(value)
      if (selected && current.work_arrangements.length === 1) return current
      return {
        ...current,
        work_arrangements: selected
          ? current.work_arrangements.filter((item) => item !== value)
          : [...current.work_arrangements, value],
      }
    })
  }

  async function save() {
    setStatus({ kind: 'saving', message: 'Saving…' })
    try {
      const response = await fetch('/api/preferences', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'save',
          preferences: {
            ...preferences,
            target_roles: parseList(targetRoles),
            priority_locations: parseList(locations),
            excluded_keywords: parseList(excludedKeywords),
            excluded_companies: parseList(excludedCompanies),
          },
        }),
      })
      const payload = (await response.json()) as { ok?: boolean; data?: SearchPreferences; error?: string }
      if (!response.ok || !payload.ok || !payload.data) {
        throw new Error(payload.error || `HTTP ${response.status}`)
      }
      setPreferences(payload.data)
      setTargetRoles(listText(payload.data.target_roles))
      setLocations(listText(payload.data.priority_locations))
      setExcludedKeywords(listText(payload.data.excluded_keywords))
      setExcludedCompanies(listText(payload.data.excluded_companies))
      setStatus({ kind: 'ok', message: 'Saved. The next search and Daily Queue will use this profile.' })
    } catch (error) {
      setStatus({ kind: 'error', message: error instanceof Error ? error.message : 'Could not save.' })
    }
  }

  return (
    <section className="workspacePanel settingsPanel searchProfilePanel">
      <div className="panelHeading">
        <div>
          <div className="eyebrow">Search profile</div>
          <h2>Tell the app what good looks like</h2>
          <p>These choices guide discovery and ranking. They never submit an application.</p>
        </div>
        <div className="queueLimitBadge">{preferences.daily_queue_size} roles / day</div>
      </div>

      <div className="preferenceForm">
        <label>
          Target roles
          <textarea value={targetRoles} onChange={(event) => setTargetRoles(event.target.value)} rows={5} placeholder="One role per line" />
          <small>Use job titles or role families, one per line.</small>
        </label>
        <label>
          Priority locations
          <textarea value={locations} onChange={(event) => setLocations(event.target.value)} rows={5} placeholder="Vilnius&#10;Remote EU" />
          <small>The app still checks location eligibility before recommending a role.</small>
        </label>

        <fieldset>
          <legend>Work setup</legend>
          <div className="preferenceChecks">
            {workArrangementValues.map((value) => (
              <label key={value}>
                <input
                  type="checkbox"
                  checked={preferences.work_arrangements.includes(value)}
                  onChange={() => toggleArrangement(value)}
                />
                <span>{arrangementLabels[value]}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <div className="preferenceInlineFields">
          <label>
            Minimum monthly salary (EUR)
            <input
              type="number"
              min="0"
              max="100000"
              step="100"
              value={preferences.minimum_salary_eur_monthly ?? ''}
              onChange={(event) => setPreferences((current) => ({
                ...current,
                minimum_salary_eur_monthly: event.target.value ? Number(event.target.value) : null,
              }))}
              placeholder="Optional"
            />
            <small>Used only when a role clearly publishes a EUR salary.</small>
          </label>
          <label>
            Daily Queue size
            <select
              value={preferences.daily_queue_size}
              onChange={(event) => setPreferences((current) => ({ ...current, daily_queue_size: Number(event.target.value) }))}
            >
              {[5, 6, 7, 8, 9, 10].map((size) => <option key={size} value={size}>{size} roles</option>)}
            </select>
            <small>A short list protects focus. The archive still keeps every role.</small>
          </label>
        </div>

        <details>
          <summary>Exclusions</summary>
          <div className="preferenceExclusions">
            <label>
              Excluded keywords
              <textarea value={excludedKeywords} onChange={(event) => setExcludedKeywords(event.target.value)} rows={4} placeholder="One phrase per line" />
            </label>
            <label>
              Excluded companies
              <textarea value={excludedCompanies} onChange={(event) => setExcludedCompanies(event.target.value)} rows={4} placeholder="One company per line" />
            </label>
          </div>
        </details>
      </div>

      <div className="preferenceActions">
        <button className="button" type="button" disabled={status.kind === 'saving'} onClick={save}>
          {status.kind === 'saving' ? 'Saving…' : 'Save search profile'}
        </button>
        {status.message ? <span className={status.kind === 'error' ? 'errorText' : status.kind === 'ok' ? 'okText' : 'muted'} role="status">{status.message}</span> : null}
      </div>
    </section>
  )
}
