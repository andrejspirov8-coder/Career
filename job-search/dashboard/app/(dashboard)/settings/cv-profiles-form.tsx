'use client'

import { useState } from 'react'

import type { VariantProfilesConfig, VariantProfile } from '@/lib/cv-profiles-types'

function listText(values: string[]) {
  return values.join('\n')
}

function parseList(value: string) {
  return value.split('\n').map((item) => item.trim()).filter(Boolean)
}

function variantSlug(slug: string): string {
  const labels: Record<string, string> = {
    'luxury-retail': 'Luxury Retail',
    'luxury-retail-lt': 'Luxury Retail (LT)',
    'operations-management': 'Operations Management',
    'operations-management-lt': 'Operations Management (LT)',
    'business-process-operations': 'Business Process Ops',
    'it-business': 'IT Business',
  }
  return labels[slug] || slug
}

export default function CvProfilesForm({ initialConfig }: { initialConfig: VariantProfilesConfig }) {
  const [config, setConfig] = useState(initialConfig)
  const [status, setStatus] = useState<{ kind: 'idle' | 'saving' | 'ok' | 'error'; message: string }>({
    kind: 'idle',
    message: '',
  })

  function updateVariant(slug: string, field: string, value: unknown) {
    setConfig((current) => {
      const raw = JSON.parse(JSON.stringify(current)) as Record<string, unknown>
      const variants = raw.variants as Record<string, Record<string, unknown>>
      if (variants[slug]) variants[slug][field] = value
      return raw as unknown as VariantProfilesConfig
    })
  }

  async function save() {
    setStatus({ kind: 'saving', message: 'Saving…' })
    try {
      const response = await fetch('/api/cv-profiles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'save', profiles: config }),
      })
      const payload = (await response.json()) as { ok?: boolean; data?: VariantProfilesConfig; error?: string }
      if (!response.ok || !payload.ok || !payload.data) {
        throw new Error(payload.error || `HTTP ${response.status}`)
      }
      setConfig(payload.data)
      setStatus({ kind: 'ok', message: 'CV profiles saved.' })
    } catch (error) {
      setStatus({ kind: 'error', message: error instanceof Error ? error.message : 'Could not save.' })
    }
  }

  const entries = Object.entries(config?.variants || {}).sort(
    ([, a], [, b]) => a.display_order - b.display_order,
  )

  return (
    <section className="workspacePanel settingsPanel cvProfilesPanel">
      <div className="panelHeading">
        <div>
          <div className="eyebrow">CV variants</div>
          <h2>CV profiles</h2>
          <p>Matching keywords, target titles, and focus for each CV variant.</p>
        </div>
      </div>

      {status.message ? (
        <div className={`sourceStatus ${status.kind === 'error' ? 'errorText' : status.kind === 'ok' ? 'okText' : 'muted'}`} role="status">
          {status.message}
        </div>
      ) : null}

      <div className="cvProfileList">
        {entries.map(([slug, variant]) => (
          <VariantCard key={slug} slug={slug} variant={variant} onUpdate={updateVariant} />
        ))}
      </div>

      <div className="sourceActions">
        <button className="button" type="button" disabled={status.kind === 'saving'} onClick={save}>
          {status.kind === 'saving' ? 'Saving…' : 'Save CV profiles'}
        </button>
      </div>
    </section>
  )
}

function VariantCard({
  slug,
  variant,
  onUpdate,
}: {
  slug: string
  variant: VariantProfile
  onUpdate: (slug: string, field: string, value: unknown) => void
}) {
  const [focus, setFocus] = useState(variant.focus)
  const [targets, setTargets] = useState(listText(variant.target_titles))
  const [keywords, setKeywords] = useState(listText(variant.keywords))
  const [negative, setNegative] = useState(listText(variant.negative_keywords))

  return (
    <details className="cvProfileCard">
      <summary>
        <span className="cvProfileName">{variant.name}</span>
        <span className="cvProfileMeta">{variant.language} · order {variant.display_order}</span>
      </summary>
      <div className="cvProfileFields">
        <label>
          Focus
          <textarea
            rows={2}
            value={focus}
            onChange={(e) => { setFocus(e.target.value); onUpdate(slug, 'focus', e.target.value) }}
          />
        </label>
        <label>
          Target titles (one per line)
          <textarea
            rows={4}
            value={targets}
            onChange={(e) => { setTargets(e.target.value); onUpdate(slug, 'target_titles', parseList(e.target.value)) }}
          />
        </label>
        <label>
          Matching keywords
          <textarea
            rows={4}
            value={keywords}
            onChange={(e) => { setKeywords(e.target.value); onUpdate(slug, 'keywords', parseList(e.target.value)) }}
          />
        </label>
        <label>
          Negative keywords
          <textarea
            rows={3}
            value={negative}
            onChange={(e) => { setNegative(e.target.value); onUpdate(slug, 'negative_keywords', parseList(e.target.value)) }}
          />
        </label>
      </div>
    </details>
  )
}
