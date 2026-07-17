'use client'

import Link from 'next/link'
import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'

import type { AutomationKind, AutomationOverview, AutomationRun, DailySearchJob } from '../../lib/automation-data'
import { safeExternalHttpUrl } from '../../lib/safe-url'

type ApiResponse<T> = { ok?: boolean; data?: T; error?: string }

const terminalStatuses = new Set(['succeeded', 'partial', 'failed', 'cancelled'])

function formatDate(value?: string | null): string {
  if (!value) return 'Not yet'
  return new Date(value).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })
}

function kindLabel(kind: AutomationKind): string {
  return kind === 'daily_search' ? 'Daily job search' : 'Rebuild CV library'
}

function statusLabel(status: AutomationRun['status']): string {
  return status.replaceAll('_', ' ')
}

function triggerLabel(trigger: string): string {
  if (trigger === 'schedule_catch_up') return 'catch-up after wake'
  return trigger.replaceAll('_', ' ')
}

export default function AutomationConsole({ initialOverview }: { initialOverview: AutomationOverview }) {
  const [overview, setOverview] = useState(initialOverview)
  const [selectedRunId, setSelectedRunId] = useState(initialOverview.active_runs[0]?.run_id || initialOverview.recent_runs[0]?.run_id || '')
  const [scheduleEnabled, setScheduleEnabled] = useState(initialOverview.settings.schedule_enabled)
  const [scheduleTime, setScheduleTime] = useState(initialOverview.settings.schedule_time)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const refresh = useCallback(async () => {
    const response = await fetch('/api/automation/overview', { cache: 'no-store' })
    const payload = (await response.json()) as ApiResponse<AutomationOverview>
    if (!response.ok || !payload.ok || !payload.data) {
      throw new Error(payload.error || 'Automation status could not be refreshed.')
    }
    setOverview(payload.data)
    setSelectedRunId((current) => current || payload.data?.active_runs[0]?.run_id || payload.data?.recent_runs[0]?.run_id || '')
  }, [])

  useEffect(() => {
    const interval = window.setInterval(() => {
      refresh().catch(() => undefined)
    }, overview.active_runs.length ? 2500 : 12000)
    return () => window.clearInterval(interval)
  }, [overview.active_runs.length, refresh])

  const selectedRun = useMemo(
    () => overview.recent_runs.find((run) => run.run_id === selectedRunId) || overview.active_runs[0] || overview.recent_runs[0],
    [overview, selectedRunId],
  )

  async function postAction(body: Record<string, unknown>) {
    const response = await fetch('/api/automation/actions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const payload = (await response.json()) as ApiResponse<unknown>
    if (!response.ok || !payload.ok) throw new Error(payload.error || 'Automation action failed.')
    return payload.data
  }

  async function start(kind: AutomationKind) {
    setBusy(kind)
    setError('')
    setNotice('')
    try {
      const data = (await postAction({ action: 'start', kind })) as { run?: AutomationRun; created?: boolean }
      if (data.run?.run_id) setSelectedRunId(data.run.run_id)
      setNotice(data.created === false ? 'That task is already active, so no duplicate was created.' : `${kindLabel(kind)} was queued.`)
      await refresh()
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : 'Automation could not be started.')
    } finally {
      setBusy('')
    }
  }

  async function changeRun(action: 'cancel' | 'retry', runId: string) {
    setBusy(`${action}:${runId}`)
    setError('')
    setNotice('')
    try {
      const data = (await postAction({ action, runId })) as { run?: AutomationRun }
      if (data.run?.run_id) setSelectedRunId(data.run.run_id)
      setNotice(action === 'cancel' ? 'Cancellation requested.' : 'A safe retry was queued.')
      await refresh()
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : 'Run action failed.')
    } finally {
      setBusy('')
    }
  }

  async function saveSchedule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy('schedule')
    setError('')
    setNotice('')
    try {
      await postAction({
        action: 'save_schedule',
        enabled: scheduleEnabled,
        scheduleTime,
        timezone: 'Europe/Vilnius',
      })
      setNotice(scheduleEnabled ? `Daily search scheduled for ${scheduleTime} Europe/Vilnius.` : 'Daily schedule disabled.')
      await refresh()
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : 'Schedule could not be saved.')
    } finally {
      setBusy('')
    }
  }

  const jobs = ((selectedRun?.result.new_live_jobs || selectedRun?.result.fresh_live_matches || []) as DailySearchJob[]).slice(0, 10)
  const progress = Math.min(100, Math.max(0, selectedRun?.progress || 0))

  return (
    <>
      <div className="workspaceHeading">
        <div>
          <div className="eyebrow">Daily operations</div>
          <h1>Automation</h1>
          <p className="muted">Run the job search, watch progress, and inspect every result from one place.</p>
        </div>
        <div className={`serviceIndicator ${overview.worker.online ? 'online' : ''}`}>
          <span aria-hidden="true" />
          <div>
            <strong>{overview.worker.online ? 'Worker online' : 'Worker on demand'}</strong>
            <small>{overview.worker.online ? `Last check ${overview.worker.age_seconds || 0}s ago` : 'Manual runs still start a private worker'}</small>
          </div>
        </div>
      </div>

      {error ? <div className="banner" role="alert">{error}</div> : null}
      {notice ? <div className="noticeBanner" role="status">{notice}</div> : null}

      <section className="controlStrip" aria-label="Automation actions">
        <button className="primaryAction" disabled={Boolean(busy)} onClick={() => start('daily_search')} type="button">
          <span>Run today&apos;s search</span>
          <small>Inbox, company careers, and ATS sources</small>
        </button>
        <button className="quietAction" disabled={Boolean(busy)} onClick={() => start('cv_build')} type="button">
          <span>Rebuild all CVs</span>
          <small>Visual and ATS PDFs</small>
        </button>
        <div className="safetyNote">
          <strong>Human-controlled LinkedIn</strong>
          <span>{overview.safety.message}</span>
        </div>
      </section>

      <section className="workspacePanel sourceHealthPanel" aria-labelledby="source-health-title">
        <div className="panelHeading">
          <div>
            <div className="eyebrow">Source health</div>
            <h2 id="source-health-title">Can the search see fresh jobs?</h2>
            <p>{overview.source_health.message}</p>
          </div>
          <span className={`statusPill sourceStatus-${overview.source_health.overall_status}`}>
            {overview.source_health.overall_status.replaceAll('_', ' ')}
          </span>
        </div>
        {overview.source_health.sources.length ? (
          <div className="sourceHealthGrid">
            {overview.source_health.sources.map((source) => (
              <div key={source.source}>
                <span className={`statusDot sourceStatusDot-${source.status}`} aria-hidden="true" />
                <span>
                  <strong>{source.source.replaceAll('_', ' ')}</strong>
                  <small>{source.message}</small>
                </span>
                <em>{source.item_count} found</em>
              </div>
            ))}
          </div>
        ) : <div className="emptyState">No source check has been recorded yet. Run today&apos;s search to create one.</div>}
        {overview.source_health.last_checked_at ? (
          <p className="sourceHealthFreshness">Last checked {formatDate(overview.source_health.last_checked_at)}{typeof overview.source_health.age_hours === 'number' ? ` · ${overview.source_health.age_hours}h ago` : ''}</p>
        ) : null}
      </section>

      <div className="operationsLayout">
        <section className="workspacePanel runTimeline" aria-labelledby="run-history-title">
          <div className="panelHeading">
            <div>
              <h2 id="run-history-title">Run history</h2>
              <p>Newest activity first</p>
            </div>
            <button className="textButton" onClick={() => refresh().catch((refreshError) => setError(refreshError.message))} type="button">
              Refresh
            </button>
          </div>
          <div className="runList">
            {overview.recent_runs.length ? overview.recent_runs.map((run) => (
              <button
                className={`runListItem ${selectedRun?.run_id === run.run_id ? 'selected' : ''}`}
                key={run.run_id}
                onClick={() => setSelectedRunId(run.run_id)}
                type="button"
              >
                <span className={`statusDot status-${run.status}`} aria-hidden="true" />
                <span className="runListMain">
                  <strong>{kindLabel(run.kind)}</strong>
                  <small>{formatDate(run.requested_at)} · {triggerLabel(run.trigger_source)}</small>
                </span>
                <span className={`statusText status-${run.status}`}>{statusLabel(run.status)}</span>
              </button>
            )) : <div className="emptyState">No runs yet. Start today&apos;s search to create the first record.</div>}
          </div>
        </section>

        <section className="workspacePanel runInspector" aria-labelledby="selected-run-title">
          {selectedRun ? (
            <>
              <div className="panelHeading">
                <div>
                  <div className="eyebrow">Selected run</div>
                  <h2 id="selected-run-title">{kindLabel(selectedRun.kind)}</h2>
                  <p>{formatDate(selectedRun.started_at || selectedRun.requested_at)}</p>
                </div>
                <span className={`statusPill status-${selectedRun.status}`}>{statusLabel(selectedRun.status)}</span>
              </div>
              <div className="progressTrack" aria-label={`${progress}% complete`} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}>
                <span style={{ width: `${progress}%` }} />
              </div>
              <div className="runFacts">
                <div><span>Phase</span><strong>{selectedRun.phase.replaceAll('_', ' ')}</strong></div>
                <div><span>Attempt</span><strong>{selectedRun.attempt}</strong></div>
                <div><span>Finished</span><strong>{formatDate(selectedRun.finished_at)}</strong></div>
              </div>
              {selectedRun.error ? <div className="inlineWarning">{selectedRun.error}</div> : null}
              <div className="buttonRow">
                {!terminalStatuses.has(selectedRun.status) ? (
                  <button className="button secondary" disabled={Boolean(busy)} onClick={() => changeRun('cancel', selectedRun.run_id)} type="button">Cancel run</button>
                ) : null}
                {['failed', 'partial', 'cancelled'].includes(selectedRun.status) ? (
                  <button className="button" disabled={Boolean(busy)} onClick={() => changeRun('retry', selectedRun.run_id)} type="button">Retry safely</button>
                ) : null}
                {selectedRun.kind === 'daily_search' ? <Link className="buttonLink" href="/opportunities">Open opportunity pipeline</Link> : <Link className="buttonLink" href="/cvs">Open CV library</Link>}
              </div>
            </>
          ) : <div className="emptyState">Select a run to see its status and results.</div>}
        </section>
      </div>

      {selectedRun?.kind === 'daily_search' ? (
        <section className="workspacePanel resultSection" aria-labelledby="results-title">
          <div className="panelHeading">
            <div>
              <h2 id="results-title">Results from this run</h2>
              <p>{selectedRun.result.discovered || 0} discovered · {selectedRun.result.matched || 0} matched · {selectedRun.result.shown_count || 0} ready to review</p>
            </div>
          </div>
          {jobs.length ? (
            <div className="resultTable" role="table">
              {jobs.map((job, index) => {
                const sourceUrl = safeExternalHttpUrl(job.source_url)
                return (
                  <div className="resultRow" key={job.opportunity_id || `${job.company}-${index}`} role="row">
                    <div>
                      <strong>{job.title || 'Untitled role'}</strong>
                      <span>{job.company || 'Unknown company'} · {job.location || 'Location not provided'}</span>
                    </div>
                    <div className="resultMeta">
                      <span>{job.recommended_cv_variant || 'Review CV fit'}</span>
                      <strong>{typeof job.fit_score === 'number' ? `${Math.round(job.fit_score)}%` : '—'}</strong>
                    </div>
                    {sourceUrl ? <a href={sourceUrl} rel="noreferrer noopener" target="_blank">Open source</a> : <span className="muted small">No source link</span>}
                  </div>
                )
              })}
            </div>
          ) : <div className="emptyState">This run has no newly delivered roles. The full saved pipeline is still available under Opportunities.</div>}
        </section>
      ) : null}

      <section className="workspacePanel schedulePanel" aria-labelledby="schedule-title">
        <div>
          <div className="eyebrow">Local schedule</div>
          <h2 id="schedule-title">Start each morning automatically</h2>
          <p className="muted">The schedule runs while the Career dashboard service is open. Your Mac must be awake and online.</p>
          <Link className="textButton notificationButton" href="/notifications">Manage inbox and desktop alerts</Link>
        </div>
        <form className="scheduleForm" onSubmit={saveSchedule}>
          <label className="toggleLabel">
            <input checked={scheduleEnabled} onChange={(event) => setScheduleEnabled(event.target.checked)} type="checkbox" />
            <span>Daily schedule enabled</span>
          </label>
          <label>
            Start time
            <input aria-label="Daily schedule time" disabled={!scheduleEnabled} onChange={(event) => setScheduleTime(event.target.value)} type="time" value={scheduleTime} />
          </label>
          <div className="scheduleTimezone"><span>Timezone</span><strong>Europe/Vilnius</strong></div>
          <button className="button" disabled={busy === 'schedule'} type="submit">{busy === 'schedule' ? 'Saving…' : 'Save schedule'}</button>
        </form>
      </section>
    </>
  )
}
