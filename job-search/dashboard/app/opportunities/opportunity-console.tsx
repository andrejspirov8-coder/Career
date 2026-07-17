'use client'

import { useEffect, useMemo, useState } from 'react'
import type {
  OpportunityCaptureResult,
  OpportunityActionResult,
  OpportunityOverview,
  OpportunityRow,
} from '../../lib/opportunity-data'
import {
  ActionNotice,
  FilterSelect,
  FunnelStep,
  OpportunityDetail,
  OpportunityListItem,
  ViewButton,
  uniqueOptions,
} from '../../features/opportunities/opportunity-components'
import { isOpportunityId } from '../../lib/opportunity-shared'
import {
  buildOpportunityActionPayload,
  filterOpportunityRows,
  firstNonEmptyOpportunityView,
  moveOpportunitySelection,
  nextOpportunitySelection,
  opportunityViewLabels,
  opportunityViewOrder,
  rowsForOpportunityView,
  type OpportunityActionPayload,
  type OpportunityFilters,
  type OpportunityViewKey,
} from '../../lib/opportunity-triage'

const primaryViews = opportunityViewOrder.slice(0, 8)
const secondaryViews = opportunityViewOrder.slice(8)
const archivePageSize = 25

type InitialOpportunityUiState = {
  view?: string
  opportunity?: string
  query?: string
  sourceKind?: string
  variant?: string
  status?: string
  risk?: string
  page?: string
}

export default function OpportunityConsole({
  initialOverview,
  initialUiState = {},
}: {
  initialOverview: OpportunityOverview
  initialUiState?: InitialOpportunityUiState
}) {
  const [overview, setOverview] = useState(initialOverview)
  const [activeView, setActiveView] = useState<OpportunityViewKey>(() => (
    opportunityViewOrder.includes(initialUiState.view as OpportunityViewKey)
      ? initialUiState.view as OpportunityViewKey
      : firstNonEmptyOpportunityView(initialOverview)
  ))
  const [busy, setBusy] = useState<string | null>(null)
  const [hydrated, setHydrated] = useState(false)
  const [result, setResult] = useState<OpportunityActionResult | { error: string } | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(() => (
    isOpportunityId(initialUiState.opportunity) ? initialUiState.opportunity : null
  ))
  const [selectedDetail, setSelectedDetail] = useState<OpportunityRow | null>(null)
  const [detailError, setDetailError] = useState('')
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailRefreshKey, setDetailRefreshKey] = useState(0)
  const [page, setPage] = useState(() => {
    const parsed = Number(initialUiState.page || 1)
    return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : 1
  })
  const [capture, setCapture] = useState({ url: '', text: '', title: '', company: '', location: '' })
  const [captureBusy, setCaptureBusy] = useState(false)
  const [captureMessage, setCaptureMessage] = useState('')
  const [filters, setFilters] = useState<OpportunityFilters>({
    query: (initialUiState.query || '').slice(0, 160),
    sourceKind: initialUiState.sourceKind || 'all',
    variant: initialUiState.variant || 'all',
    status: initialUiState.status || 'all',
    risk: ['flagged', 'clean'].includes(initialUiState.risk || '')
      ? initialUiState.risk as OpportunityFilters['risk']
      : 'all',
  })

  useEffect(() => setHydrated(true), [])

  const allRows = overview.queues.all
  const viewRows = useMemo(() => rowsForOpportunityView(overview, activeView), [activeView, overview])
  const rows = useMemo(() => filterOpportunityRows(viewRows, filters), [filters, viewRows])
  const totalPages = Math.max(1, Math.ceil(rows.length / archivePageSize))
  const visibleRows = useMemo(
    () => rows.slice((page - 1) * archivePageSize, page * archivePageSize),
    [page, rows],
  )
  const selected = useMemo(
    () => allRows.find((row) => row.opportunity_id === selectedId) || visibleRows[0] || null,
    [allRows, selectedId, visibleRows],
  )
  const sourceOptions = useMemo(() => uniqueOptions(allRows.map((row) => row.source_kind)), [allRows])
  const variantOptions = useMemo(() => uniqueOptions(allRows.map((row) => row.match?.best_variant)), [allRows])
  const statusOptions = useMemo(() => uniqueOptions(allRows.map((row) => row.status)), [allRows])

  useEffect(() => setSelectedId(selected?.opportunity_id || null), [selected])

  useEffect(() => {
    function handleKeyboardNavigation(event: KeyboardEvent) {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey || busy) return
      const target = event.target
      if (target instanceof HTMLElement && (
        target.isContentEditable
        || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
      )) return

      const key = event.key.toLowerCase()
      if (key !== 'j' && key !== 'k') return
      const nextId = moveOpportunitySelection(visibleRows, selectedId, key === 'j' ? 1 : -1)
      if (!nextId) return
      event.preventDefault()
      setSelectedId(nextId)
    }

    window.addEventListener('keydown', handleKeyboardNavigation)
    return () => window.removeEventListener('keydown', handleKeyboardNavigation)
  }, [busy, selectedId, visibleRows])

  useEffect(() => {
    if (page > totalPages) setPage(totalPages)
  }, [page, totalPages])

  useEffect(() => {
    if (!hydrated) return
    const params = new URLSearchParams()
    if (activeView !== 'daily_queue') params.set('view', activeView)
    if (selectedId) params.set('opportunity', selectedId)
    if (filters.query) params.set('q', filters.query)
    if (filters.sourceKind !== 'all') params.set('source', filters.sourceKind)
    if (filters.variant !== 'all') params.set('cv', filters.variant)
    if (filters.status !== 'all') params.set('status', filters.status)
    if (filters.risk !== 'all') params.set('risk', filters.risk)
    if (page > 1) params.set('page', String(page))
    const query = params.toString()
    window.history.replaceState(null, '', `${window.location.pathname}${query ? `?${query}` : ''}`)
  }, [activeView, filters, hydrated, page, selectedId])

  useEffect(() => {
    const opportunityId = selected?.opportunity_id
    if (!opportunityId) {
      setSelectedDetail(null)
      setDetailError('')
      return
    }

    const controller = new AbortController()
    setSelectedDetail(null)
    setDetailError('')
    setDetailLoading(true)
    void fetch(`/api/opportunities/${encodeURIComponent(opportunityId)}`, {
      cache: 'no-store',
      signal: controller.signal,
    })
      .then(async (response) => {
        const payload = (await response.json()) as { ok?: boolean; data?: OpportunityRow; error?: string }
        if (!response.ok || !payload.ok || !payload.data) {
          throw new Error(payload.error || `HTTP ${response.status}`)
        }
        setSelectedDetail(payload.data)
      })
      .catch((error) => {
        if (error instanceof DOMException && error.name === 'AbortError') return
        setDetailError(error instanceof Error ? error.message : 'Opportunity detail failed.')
      })
      .finally(() => {
        if (!controller.signal.aborted) setDetailLoading(false)
      })

    return () => controller.abort()
  }, [detailRefreshKey, selected?.opportunity_id])

  async function refresh(): Promise<OpportunityOverview | null> {
    const response = await fetch('/api/opportunities/overview', { cache: 'no-store' })
    const data = await response.json()
    if (!response.ok) {
      setResult({ error: data?.error || `HTTP ${response.status}` })
      return null
    }
    const next = data as OpportunityOverview
    setOverview(next)
    setActiveView((current) => rowsForOpportunityView(next, current).length ? current : firstNonEmptyOpportunityView(next))
    return next
  }

  async function postAction(payload: OpportunityActionPayload) {
    const rowsBeforeAction = visibleRows
    const selectedBeforeAction = selected?.opportunity_id || selectedId
    setBusy(payload.action)
    setResult(null)
    try {
      const response = await fetch('/api/opportunities/actions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const data = (await response.json()) as { ok: boolean; data?: OpportunityActionResult; error?: string }
      if (!response.ok || !data.ok) {
        setResult({ error: data.error || `HTTP ${response.status}` })
      } else {
        setResult(data.data || {})
        const next = await refresh()
        if (next) {
          const nextView = rowsForOpportunityView(next, activeView).length
            ? activeView
            : firstNonEmptyOpportunityView(next)
          const filteredNextRows = filterOpportunityRows(rowsForOpportunityView(next, nextView), filters)
          const nextPageCount = Math.max(1, Math.ceil(filteredNextRows.length / archivePageSize))
          const nextPage = nextView === activeView ? Math.min(page, nextPageCount) : 1
          const firstRowIndex = (nextPage - 1) * archivePageSize
          const nextVisibleRows = filteredNextRows.slice(firstRowIndex, firstRowIndex + archivePageSize)
          setActiveView(nextView)
          setPage(nextPage)
          setSelectedId(nextOpportunitySelection(rowsBeforeAction, nextVisibleRows, selectedBeforeAction))
        }
        setDetailRefreshKey((current) => current + 1)
      }
    } catch (error) {
      setResult({ error: error instanceof Error ? error.message : 'Action failed.' })
    } finally {
      setBusy(null)
    }
  }

  async function captureJob() {
    setCaptureBusy(true)
    setCaptureMessage('')
    try {
      const response = await fetch('/api/opportunities/capture', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(capture),
      })
      const data = (await response.json()) as { ok?: boolean; data?: OpportunityCaptureResult; error?: string }
      if (!response.ok || !data.ok || !data.data) throw new Error(data.error || `HTTP ${response.status}`)
      await refresh()
      setActiveView(data.data.status === 'apply_ready' ? 'stage_shortlisted' : 'stage_review')
      setSelectedId(data.data.opportunity_id)
      setPage(1)
      setCapture({ url: '', text: '', title: '', company: '', location: '' })
      setCaptureMessage('Saved and matched. The link was not fetched; review the evidence before acting.')
    } catch (error) {
      setCaptureMessage(error instanceof Error ? error.message : 'Could not capture this job.')
    } finally {
      setCaptureBusy(false)
    }
  }

  async function applySuggestion(suggestion: NonNullable<OpportunityActionResult['preference_suggestion']>) {
    setBusy('apply_preference_suggestion')
    try {
      const response = await fetch('/api/preferences', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'apply_suggestion', suggestion }),
      })
      const data = (await response.json()) as { ok?: boolean; error?: string }
      if (!response.ok || !data.ok) throw new Error(data.error || `HTTP ${response.status}`)
      setResult({ ok: true, preference_updated: true })
      await refresh()
      setDetailRefreshKey((current) => current + 1)
    } catch (error) {
      setResult({ error: error instanceof Error ? error.message : 'Preference update failed.' })
    } finally {
      setBusy(null)
    }
  }

  function updateFilter<K extends keyof OpportunityFilters>(key: K, value: OpportunityFilters[K]) {
    setFilters((current) => ({ ...current, [key]: value }))
    setPage(1)
  }

  function selectView(view: OpportunityViewKey) {
    setActiveView(view)
    setSelectedId(null)
    setPage(1)
  }

  return (
    <>
      {overview.helperError ? <div className="banner">{overview.helperError}</div> : null}

      <details className="workspacePanel capturePanel">
        <summary>
          <span>Capture a job</span>
          <small>Paste a link or job text. The server will not open the link.</small>
        </summary>
        <div className="captureForm">
          <label className="captureUrlField">
            Job link
            <input value={capture.url} onChange={(event) => setCapture((current) => ({ ...current, url: event.target.value }))} placeholder="https://company.example/jobs/…" />
          </label>
          <label>
            Job title <small>optional</small>
            <input value={capture.title} onChange={(event) => setCapture((current) => ({ ...current, title: event.target.value }))} maxLength={200} />
          </label>
          <label>
            Company <small>optional</small>
            <input value={capture.company} onChange={(event) => setCapture((current) => ({ ...current, company: event.target.value }))} maxLength={200} />
          </label>
          <label>
            Location <small>optional</small>
            <input value={capture.location} onChange={(event) => setCapture((current) => ({ ...current, location: event.target.value }))} maxLength={200} />
          </label>
          <label className="captureTextField">
            Job text <small>optional if you pasted a link</small>
            <textarea value={capture.text} onChange={(event) => setCapture((current) => ({ ...current, text: event.target.value }))} maxLength={50000} rows={7} placeholder="Paste the job description, or the existing TITLE / COMPANY / URL format." />
          </label>
          <div className="captureActions">
            <button className="button" type="button" disabled={captureBusy || (!capture.url.trim() && !capture.text.trim())} onClick={captureJob}>
              {captureBusy ? 'Saving and matching…' : 'Save and match'}
            </button>
            {captureMessage ? <span className={captureMessage.startsWith('Saved') ? 'okText' : 'errorText'} role="status">{captureMessage}</span> : null}
          </div>
        </div>
      </details>

      <section className="pipelineOverview" aria-label="Opportunity funnel">
        <div className="pipelineOverviewHeading">
          <div>
            <div className="eyebrow">Daily decision funnel</div>
            <h2>
              {overview.counts.daily_queue
                ? overview.counts.daily_queue === 1
                  ? '1 role deserves attention today'
                  : `${overview.counts.daily_queue} roles deserve attention today`
                : overview.funnel.shortlisted === 1
                  ? '1 shortlisted role is waiting for your decision'
                  : overview.funnel.shortlisted > 1
                    ? `${overview.funnel.shortlisted} shortlisted roles are waiting for your decision`
                    : 'No high-confidence role needs action yet'}
            </h2>
            <p>Your saved search profile ranks a focused queue of up to {overview.search_profile?.daily_queue_size || 5} roles.</p>
          </div>
          <button className="button secondary" type="button" disabled={!hydrated || Boolean(busy)} onClick={refresh}>Refresh</button>
        </div>
        <div className="funnelBand">
          <FunnelStep label="Found" value={overview.funnel.discovered} />
          <FunnelStep label="Unique" value={overview.funnel.deduplicated} />
          <FunnelStep label="Location fit" value={overview.funnel.location_fit} />
          <FunnelStep label="Role fit" value={overview.funnel.role_fit} />
          <FunnelStep label="Shortlisted" value={overview.funnel.shortlisted} />
          <FunnelStep label="Apply ready" value={overview.funnel.apply_ready} />
        </div>
      </section>

      <section className="pipelineStages" aria-label="Application stages">
        {primaryViews.map((view) => (
          <ViewButton key={view} view={view} activeView={activeView} overview={overview} onSelect={selectView} />
        ))}
      </section>

      <details className="advancedControls section">
        <summary>More queues and filters</summary>
        <div className="tabs advancedTabs">
          {secondaryViews.map((view) => (
            <ViewButton key={view} view={view} activeView={activeView} overview={overview} onSelect={selectView} />
          ))}
        </div>
        <div className="filterBar">
          <label>
            Search
            <input value={filters.query} onChange={(event) => updateFilter('query', event.target.value)} placeholder="Role or company" />
          </label>
          <FilterSelect label="Source" value={filters.sourceKind} options={sourceOptions} onChange={(value) => updateFilter('sourceKind', value)} />
          <FilterSelect label="CV" value={filters.variant} options={variantOptions} onChange={(value) => updateFilter('variant', value)} />
          <FilterSelect label="Status" value={filters.status} options={statusOptions} onChange={(value) => updateFilter('status', value)} />
          <label>
            Attention
            <select value={filters.risk} onChange={(event) => updateFilter('risk', event.target.value as OpportunityFilters['risk'])}>
              <option value="all">All</option>
              <option value="flagged">Needs attention</option>
              <option value="clean">Clear</option>
            </select>
          </label>
        </div>
      </details>

      {result ? (
        <ActionNotice
          result={result}
          busy={busy}
          onUndo={(opportunityId) => postAction(buildOpportunityActionPayload('undo_last_decision', { opportunityId }))}
          onApplySuggestion={applySuggestion}
        />
      ) : null}

      <section className="triageLayout opportunityTriage">
        <div className="queueList" aria-live="polite">
          <div className="queueListHeading">
            <div>
              <span>{opportunityViewLabels[activeView]}</span>
              <strong>{rows.length} {rows.length === 1 ? 'role' : 'roles'}</strong>
            </div>
            <small>Choose a role to see why it matched. Press <kbd>J</kbd>/<kbd>K</kbd> to move.</small>
          </div>
          {rows.length ? visibleRows.map((row) => (
            <OpportunityListItem
              key={`${activeView}-${row.opportunity_id}`}
              row={row}
              selected={selected?.opportunity_id === row.opportunity_id}
              onSelect={() => setSelectedId(row.opportunity_id)}
            />
          )) : (
            <div className="emptyState workspacePanel">Nothing needs attention in this stage.</div>
          )}
          {totalPages > 1 ? (
            <div className="pagination" aria-label="Opportunity pages">
              <button className="button secondary" type="button" disabled={page <= 1} onClick={() => setPage((current) => Math.max(1, current - 1))}>Previous</button>
              <span>Page {page} of {totalPages}</span>
              <button className="button secondary" type="button" disabled={page >= totalPages} onClick={() => setPage((current) => Math.min(totalPages, current + 1))}>Next</button>
            </div>
          ) : null}
        </div>

        <OpportunityDetail
          row={selectedDetail}
          summary={selected}
          loading={detailLoading}
          error={detailError}
          busy={busy}
          onAction={postAction}
        />
      </section>
    </>
  )
}
