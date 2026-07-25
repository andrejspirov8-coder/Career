'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import {
  ActionResult,
  FilterSelect,
  MetricRow,
  ProfileDetail,
  RecentRuns,
  RunStatus,
  approvalLabel,
  commandText,
  firstNonEmptyView,
  formatScore,
  isSentRow,
  uniqueOptions,
  uniqueProfileRows,
} from '@/features/recruiters/recruiter-components'
import {
  buildRecruiterActionPayload,
  filterTriageRows,
  rowsForSavedView,
  savedViewLabels,
  savedViewOrder,
  type RecruiterActionPayload,
  type SavedViewKey,
  type TriageFilters,
} from '@/lib/recruiter-triage'
import type {
  RecruiterActionResult,
  RecruiterOverview,
  RecruiterQueueRow,
  RecruiterRunActionName,
} from '@/lib/recruiter-data'

type ActionResultState = RecruiterActionResult | { error: string }

const runActions: Array<{ action: RecruiterRunActionName; label: string }> = [
  { action: 'preflight', label: 'Run Preflight' },
  { action: 'rank_existing', label: 'Rank Existing Results' },
]

export default function RecruiterConsole({ initialOverview, initialQuery = '' }: { initialOverview: RecruiterOverview; initialQuery?: string }) {
  const [overview, setOverview] = useState(initialOverview)
  const [activeView, setActiveView] = useState<SavedViewKey>(() => firstNonEmptyView(initialOverview))
  const [busy, setBusy] = useState<string | null>(null)
  const [hydrated, setHydrated] = useState(false)
  const [result, setResult] = useState<ActionResultState | null>(null)
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [selectedProfileUrl, setSelectedProfileUrl] = useState<string | null>(null)
  const [selectedUrls, setSelectedUrls] = useState<Set<string>>(() => new Set())
  const [filters, setFilters] = useState<TriageFilters>({
    query: initialQuery,
    persona: 'all',
    variant: 'all',
    riskFlag: 'all',
    approval: 'all',
  })

  useEffect(() => setHydrated(true), [])

  const allRows = useMemo(
    () => uniqueProfileRows(savedViewOrder.flatMap((view) => rowsForSavedView(overview, view))),
    [overview],
  )
  const viewRows = useMemo(() => rowsForSavedView(overview, activeView), [activeView, overview])
  const rows = useMemo(() => filterTriageRows(viewRows, filters), [filters, viewRows])
  const selectedProfile = useMemo(
    () => rows.find((row) => row.profile_url === selectedProfileUrl) || rows[0] || null,
    [rows, selectedProfileUrl],
  )
  const selectedCount = selectedUrls.size
  const visibleSelectableRows = useMemo(() => rows.filter((row) => !isSentRow(row)), [rows])
  const allVisibleSelected =
    visibleSelectableRows.length > 0 && visibleSelectableRows.every((row) => selectedUrls.has(row.profile_url))

  useEffect(() => {
    if (selectedProfile) {
      setSelectedProfileUrl(selectedProfile.profile_url)
    } else {
      setSelectedProfileUrl(null)
    }
  }, [selectedProfile])

  const personaOptions = useMemo(() => uniqueOptions(allRows.map((row) => row.persona)), [allRows])
  const variantOptions = useMemo(() => uniqueOptions(allRows.map((row) => row.cv_variant)), [allRows])
  const riskOptions = useMemo(() => uniqueOptions(allRows.flatMap((row) => row.risk_flags || [])), [allRows])
  const approvalRate = overview.counts.auto_send ? `${overview.counts.approved_notes}/${overview.counts.auto_send}` : '0/0'
  const responseRate = overview.counts.sent ? `${Math.round((overview.counts.reply / overview.counts.sent) * 100)}%` : '0%'
  const personaRows = useMemo(() => Object.entries(overview.metrics.personas).slice(0, 8), [overview.metrics.personas])
  const riskRows = useMemo(() => Object.entries(overview.metrics.risk_flags).slice(0, 8), [overview.metrics.risk_flags])
  const opportunityTargets = overview.opportunity_targets?.companies || []

  async function refresh() {
    const response = await fetch('/api/recruiter/overview', { cache: 'no-store' })
    const data = await response.json()
    if (!response.ok) {
      setResult({ error: data?.error || `HTTP ${response.status}` })
      return
    }
    const next = data as RecruiterOverview
    setOverview(next)
    setActiveView((current) => (rowsForSavedView(next, current).length ? current : firstNonEmptyView(next)))
  }

  async function postAction(payload: RecruiterActionPayload) {
    setBusy(payload.action)
    setResult(null)
    try {
      const response = await fetch('/api/recruiter/actions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const data = (await response.json()) as { ok: boolean; data?: RecruiterActionResult; error?: string }
      if (!response.ok || !data.ok) {
        setResult({ error: data.error || `HTTP ${response.status}` })
      } else {
        setResult(data.data || {})
        if (payload.action.startsWith('bulk_')) {
          setSelectedUrls(new Set())
        }
        await refresh()
      }
    } catch (error) {
      setResult({ error: error instanceof Error ? error.message : 'Action failed.' })
    } finally {
      setBusy(null)
    }
  }

  function draftFor(row: RecruiterQueueRow) {
    return drafts[row.profile_url] ?? row.note ?? ''
  }

  function updateDraft(row: RecruiterQueueRow, note: string) {
    setDrafts((current) => ({ ...current, [row.profile_url]: note }))
  }

  function updateFilter<K extends keyof TriageFilters>(key: K, value: TriageFilters[K]) {
    setFilters((current) => ({ ...current, [key]: value }))
  }

  function toggleSelected(profileUrl: string, checked: boolean) {
    setSelectedUrls((current) => {
      const next = new Set(current)
      if (checked) next.add(profileUrl)
      else next.delete(profileUrl)
      return next
    })
  }

  function setVisibleSelection(checked: boolean) {
    setSelectedUrls((current) => {
      const next = new Set(current)
      for (const row of visibleSelectableRows) {
        if (checked) next.add(row.profile_url)
        else next.delete(row.profile_url)
      }
      return next
    })
  }

  return (
    <>
      {overview.helperError ? <div className="banner">{overview.helperError}</div> : null}

      <section className="statusBand recruiterStatusBand">
        <div><span>Follow up</span><strong>{rowsForSavedView(overview, 'follow_up').length}</strong></div>
        <div><span>Ready to contact</span><strong>{rowsForSavedView(overview, 'ready_to_contact').length}</strong></div>
        <div><span>Needs review</span><strong>{overview.counts.queue_review}</strong></div>
        <div><span>Reply rate</span><strong>{responseRate}</strong></div>
      </section>

      <section className="workspacePanel liveDispatchBlock recruiterGuardrail">
        <div>
          <div className="eyebrow">Required human step</div>
          <h2>LinkedIn stays manual</h2>
          <p className="muted">
            Prepare the exact note here. Open the verified profile, send it yourself,
            then record what happened. The web app cannot search or send.
          </p>
        </div>
        <div className="liveDispatchStats">
          <MetricRow left="Approved notes" right={approvalRate} />
          <MetricRow left="Ready for manual send" right={String(overview.campaign?.readiness?.ready_for_manual_send ?? overview.live_dispatch?.ready_for_manual_send ?? 0)} />
          <MetricRow left="Hard daily ceiling" right="3 messages" />
        </div>
      </section>

      <section className="workspacePanel recruiterTargetPanel">
        <div className="panelHeading">
          <div>
            <div className="eyebrow">Matched jobs → recruiter discovery</div>
            <h2>Hiring companies from matched jobs</h2>
            <p>
              Recruiter discovery searches these companies before broader CV-based
              searches. It finds profiles only; it never sends messages.
            </p>
          </div>
          <span className="statusPill">
            {opportunityTargets.length} compan{opportunityTargets.length === 1 ? 'y' : 'ies'}
          </span>
        </div>
        {overview.opportunity_targets?.error ? (
          <p className="errorText small">The matched-job targets could not be read safely.</p>
        ) : opportunityTargets.length ? (
          <div className="recruiterTargetList">
            {opportunityTargets.map((target) => (
              <article className="recruiterTargetRow" key={target.opportunity_id}>
                <div>
                  <strong>{target.company}</strong>
                  <span>{target.title}</span>
                  <small>{target.location || 'Location not recorded'}</small>
                </div>
                <div className="recruiterTargetMeta">
                  <span>{target.cv_variant}</span>
                  <span>Fit {formatScore(target.fit_score)}</span>
                  <span>{target.priority_reason.replaceAll('_', ' ')}</span>
                </div>
                <Link
                  className="textButton"
                  href={`/opportunities?opportunity=${encodeURIComponent(target.opportunity_id)}`}
                >
                  Open job
                </Link>
              </article>
            ))}
          </div>
        ) : (
          <p className="emptyState">
            No fresh, eligible matched jobs are ready for company-specific recruiter
            discovery. Refresh the opportunity search first.
          </p>
        )}
      </section>

      {overview.risk_stop_state?.stopped ? (
        <section className="section card banner">
          <h2>Stop Run</h2>
          <p>{overview.risk_stop_state.reason || 'Risk signal detected'}.</p>
        </section>
      ) : null}

      <details className="advancedControls section recruiterDataTools">
        <summary>Refresh or re-rank saved recruiter data</summary>
        <div className="buttonRow">
          {runActions.map((item) => (
            <button key={item.action} className="button" disabled={Boolean(busy)} onClick={() => postAction(buildRecruiterActionPayload(item.action))}>
              {busy === item.action ? 'Running...' : item.label}
            </button>
          ))}
          <button className="button secondary" disabled={!hydrated || Boolean(busy)} onClick={refresh}>Refresh</button>
        </div>
        <details className="commandPreview">
          <summary>Show technical commands</summary>
          {runActions.map((item) => (
            <button
              key={item.action}
              className="commandButton"
              disabled={Boolean(busy)}
              onClick={() => postAction(buildRecruiterActionPayload(item.action))}
            >
              <span>{busy === item.action ? 'Running...' : item.label}</span>
              <code>{commandText(overview, item.action)}</code>
            </button>
          ))}
        </details>
        {result ? <ActionResult result={result} /> : null}
        <div className="grid recruiterRunHistory">
          <RunStatus activeRun={overview.active_run || null} />
          <RecentRuns runs={overview.run_history || overview.recent_runs || []} />
        </div>
      </details>

      <section className="section tabs">
        {savedViewOrder.map((view) => (
          <button
            key={view}
            className={`tab ${activeView === view ? 'active' : ''}`}
            onClick={() => {
              setActiveView(view)
              setSelectedUrls(new Set())
            }}
          >
            {savedViewLabels[view]} ({rowsForSavedView(overview, view).length})
          </button>
        ))}
      </section>

      <section className="section filterBar">
        <label>
          Search
          <input value={filters.query} onChange={(event) => updateFilter('query', event.target.value)} placeholder="Name, profile, note" />
        </label>
        <FilterSelect label="Persona" value={filters.persona} options={personaOptions} onChange={(value) => updateFilter('persona', value)} />
        <FilterSelect label="CV" value={filters.variant} options={variantOptions} onChange={(value) => updateFilter('variant', value)} />
        <FilterSelect label="Risk" value={filters.riskFlag} options={riskOptions} onChange={(value) => updateFilter('riskFlag', value)} />
        <label>
          Approval
          <select value={filters.approval} onChange={(event) => updateFilter('approval', event.target.value as TriageFilters['approval'])}>
            <option value="all">All</option>
            <option value="approved">Approved</option>
            <option value="not_approved">Not approved</option>
          </select>
        </label>
      </section>

      <section className="bulkBar">
        <label className="selectAll">
          <input
            type="checkbox"
            checked={allVisibleSelected}
            disabled={!visibleSelectableRows.length || Boolean(busy)}
            onChange={(event) => setVisibleSelection(event.target.checked)}
          />
          Select visible
        </label>
        <span className="muted small">{selectedCount} selected</span>
        <button
          className="button secondary"
          disabled={!selectedCount || Boolean(busy)}
          onClick={() => postAction(buildRecruiterActionPayload('bulk_mark_skipped', { profileUrls: Array.from(selectedUrls) }))}
        >
          Mark Skipped
        </button>
        <button
          className="button secondary"
          disabled={!selectedCount || Boolean(busy)}
          onClick={() => postAction(buildRecruiterActionPayload('bulk_mark_review', { profileUrls: Array.from(selectedUrls) }))}
        >
          Move To Review
        </button>
      </section>

      <section className="triageLayout">
        <div className="queueList">
          {rows.length ? rows.map((row) => {
            const sent = isSentRow(row)
            const selected = selectedProfile?.profile_url === row.profile_url
            return (
              <article
                className={`queueItem ${selected ? 'selected' : ''}`}
                key={`${activeView}-${row.profile_url}`}
                role="button"
                tabIndex={0}
                onClick={() => setSelectedProfileUrl(row.profile_url)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') setSelectedProfileUrl(row.profile_url)
                }}
              >
                <div className="queueItemMain">
                  <label className="checkCell" onClick={(event) => event.stopPropagation()}>
                    <input
                      aria-label={`Select ${row.name || row.profile_url}`}
                      type="checkbox"
                      checked={selectedUrls.has(row.profile_url)}
                      disabled={sent || Boolean(busy)}
                      onChange={(event) => toggleSelected(row.profile_url, event.target.checked)}
                    />
                  </label>
                  <div className="queueSummary">
                    <div className="queueHeader">
                      <div>
                        <h2>{row.name || row.profile_url}</h2>
                        <p className="muted">{row.headline || row.company || row.profile_url}</p>
                      </div>
                      <div className="score">{formatScore(row.score_details?.rank_score ?? row.rank_score)}</div>
                    </div>
                    <div className="tagRow">
                      <span>{row.persona || 'no persona'}</span>
                      <span>{row.cv_variant || 'no CV'}</span>
                      <span>{sent ? 'sent' : row.decision || row.status || 'queued'}</span>
                      <span>{approvalLabel(row, sent)}</span>
                      {row.target_company ? (
                        <span>
                          {row.target_company_verified ? 'verified target' : 'unverified target'}: {row.target_company}
                        </span>
                      ) : null}
                    </div>
                    {row.risk_flags?.length ? <div className="riskRow">{row.risk_flags.map((flag) => <span key={flag}>{flag}</span>)}</div> : null}
                  </div>
                </div>
              </article>
            )
          }) : <div className="card muted">No rows match this view.</div>}
        </div>

        <ProfileDetail
          row={selectedProfile}
          busy={busy}
          draft={selectedProfile ? draftFor(selectedProfile) : ''}
          onDraftChange={(note) => {
            if (selectedProfile) updateDraft(selectedProfile, note)
          }}
          onAction={postAction}
        />
      </section>

      <details className="advancedControls section">
        <summary>Campaign diagnostics</summary>
        <div className="grid recruiterDiagnostics">
          <div className="card">
            <h2>Personas</h2>
            <div className="list">{personaRows.map(([name, stats]) => <MetricRow key={name} left={name} right={`${stats.queued} queued | ${stats.sent} sent`} />)}</div>
          </div>
          <div className="card">
            <h2>Risk flags</h2>
            <div className="list">{riskRows.map(([name, count]) => <MetricRow key={name} left={name} right={String(count)} />)}</div>
          </div>
        </div>
      </details>
    </>
  )
}
