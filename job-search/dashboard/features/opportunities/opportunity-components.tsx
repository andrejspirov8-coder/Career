'use client'

import { useEffect, useState } from 'react'
import type {
  OpportunityActionName,
  OpportunityActionResult,
  OpportunityOverview,
  OpportunityRow,
  OpportunitySummary,
} from '../../lib/opportunity-data'
import {
  buildOpportunityActionPayload,
  opportunityViewLabels,
  rowsForOpportunityView,
  type OpportunityActionPayload,
  type OpportunityViewKey,
} from '../../lib/opportunity-triage'
import { safeExternalHttpUrl } from '../../lib/safe-url'

export function ViewButton({
  view,
  activeView,
  overview,
  onSelect,
}: {
  view: OpportunityViewKey
  activeView: OpportunityViewKey
  overview: OpportunityOverview
  onSelect: (view: OpportunityViewKey) => void
}) {
  return (
    <button className={`pipelineStage ${activeView === view ? 'active' : ''}`} onClick={() => onSelect(view)} type="button">
      <span>{opportunityViewLabels[view]}</span>
      <strong>{rowsForOpportunityView(overview, view).length}</strong>
    </button>
  )
}

export function FunnelStep({ label, value }: { label: string; value: number }) {
  return <div><span>{label}</span><strong>{value}</strong></div>
}

export function OpportunityListItem({ row, selected, onSelect }: { row: OpportunitySummary; selected: boolean; onSelect: () => void }) {
  const blockers = row.evidence.blockers || []
  const warnings = row.evidence.warnings || []
  return (
    <article
      className={`queueItem opportunityItem ${selected ? 'selected' : ''}`}
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') onSelect()
      }}
    >
      <div className="queueHeader">
        <div>
          <div className="stageLabel">{humanize(row.stage)}</div>
          <h2>{row.title || row.company || row.opportunity_id}</h2>
          <p className="muted">{row.company} {row.location ? `· ${row.location}` : ''}</p>
        </div>
        <div className="score" aria-label={`Fit score ${formatScore(row.match?.score)}`}>{formatScore(row.match?.score)}</div>
      </div>
      <div className="opportunityMeta">
        <span>{eligibilityLabel(row.location_eligibility)}</span>
        <span>{row.match?.best_variant ? humanize(row.match.best_variant) : 'CV choice pending'}</span>
        <strong>{nextActionLabel(row.next_action)}</strong>
      </div>
      {row.preference?.reasons?.[0] ? <p className="queueReason">{row.preference.reasons[0]}</p> : null}
      {blockers.length ? <RiskLine kind="blocker" flags={blockers} /> : null}
      {!blockers.length && warnings.length ? <RiskLine kind="warning" flags={warnings} /> : null}
    </article>
  )
}

export function OpportunityDetail({
  row,
  summary,
  loading,
  error,
  busy,
  onAction,
}: {
  row: OpportunityRow | null
  summary: OpportunitySummary | null
  loading: boolean
  error: string
  busy: string | null
  onAction: (payload: OpportunityActionPayload) => void
}) {
  const [applicationUrl, setApplicationUrl] = useState('')
  const [applicationNotes, setApplicationNotes] = useState('')
  const [outcome, setOutcome] = useState('screening')
  const [skipReason, setSkipReason] = useState('')
  const [skipNote, setSkipNote] = useState('')
  const [linkCopied, setLinkCopied] = useState(false)

  useEffect(() => {
    setApplicationUrl(row?.source_url || '')
    setApplicationNotes('')
    setOutcome('screening')
    setSkipReason('')
    setSkipNote('')
    setLinkCopied(false)
  }, [row?.opportunity_id, row?.source_url])

  if (loading) return <DetailState title={summary?.title || 'Opportunity'} message="Loading the full job evidence…" />
  if (error) return <DetailState title={summary?.title || 'Opportunity'} message={error} error />
  if (!row) return <DetailState title="Opportunity" message="Choose a role to review it." />

  const history = [...(row.action_history || [])].slice(0, 8)
  const applications = [...(row.application_history || [])].reverse()
  const sourceUrl = safeExternalHttpUrl(row.source_url)
  const risk = detailRisk(row)
  const primaryAction = primaryActionFor(row, risk.blockers)
  const canLogApplication = !['skipped', 'expired'].includes(row.status)

  return (
    <aside className="detailPanel opportunityDetail">
      <div className="detailHeader">
        <div>
          <div className="stageLabel">{humanize(row.stage || row.status)}</div>
          <h2>{row.title || row.company || row.opportunity_id}</h2>
          <p className="muted">{row.company} {row.location ? `· ${row.location}` : ''}</p>
        </div>
        <div className="detailHeaderLinks">
          <button
            className="textButton"
            type="button"
            onClick={() => {
              void navigator.clipboard.writeText(window.location.href).then(() => setLinkCopied(true))
            }}
          >
            {linkCopied ? 'Link copied' : 'Copy app link'}
          </button>
          {sourceUrl ? <a href={sourceUrl} target="_blank" rel="noreferrer noopener">Open job ↗</a> : null}
        </div>
      </div>

      <section className="nextActionCard">
        <span>Recommended next action</span>
        <strong>{primaryAction.label}</strong>
        <p>{primaryAction.detail}</p>
        {primaryAction.action ? (
          <button
            className="button"
            disabled={Boolean(busy) || primaryAction.disabled}
            onClick={() => onAction(buildOpportunityActionPayload(primaryAction.action as OpportunityActionName, { opportunityId: row.opportunity_id }))}
            type="button"
          >
            {busy === primaryAction.action ? 'Working…' : primaryAction.buttonLabel}
          </button>
        ) : null}
      </section>

      {risk.blockers.length ? <RiskLine kind="blocker" flags={risk.blockers} /> : null}
      {risk.warnings.length ? <RiskLine kind="warning" flags={risk.warnings} /> : null}

      <section className="detailSection whyMatch">
        <h3>Why this role</h3>
        {row.preference?.reasons?.length ? (
          <ul className="preferenceReasons">
            {row.preference.reasons.map((reason) => <li key={reason}>{reason}</li>)}
          </ul>
        ) : null}
        <p>{row.match?.explanation.why_this_role || 'The app has not recorded a match explanation yet.'}</p>
        <p className="muted">{row.match?.explanation.why_this_cv || ''}</p>
        {row.match?.explanation.why_apply_review_or_skip ? <p className="decisionReason">{row.match.explanation.why_apply_review_or_skip}</p> : null}
      </section>

      <section className="detailSection prepWorkspace">
        <h3>Application preparation</h3>
        <div className="prepChecklist">
          <ChecklistItem done={Boolean(sourceUrl)} label="Job source is available" />
          <ChecklistItem done={Boolean(row.match?.best_variant)} label="CV variant selected" />
          <ChecklistItem done={Boolean(row.pack)} label="Application pack prepared" />
          <ChecklistItem done={Boolean(applications.length)} label="Application logged" />
        </div>
        <div className="queueActions">
          <ActionButton action="mark_apply_ready" label="Shortlist" row={row} busy={busy} onAction={onAction} disabled={row.status === 'apply_ready' || Boolean(risk.blockers.length)} />
          <ActionButton action="generate_pack" label="Generate application pack" row={row} busy={busy} onAction={onAction} disabled={row.status !== 'apply_ready'} />
        </div>
        <details className="closeDecision">
          <summary>Close as not suitable</summary>
          <div className="closeDecisionForm">
            <label>
              Why are you closing it?
              <select value={skipReason} onChange={(event) => setSkipReason(event.target.value)}>
                <option value="">Choose a reason</option>
                <option value="not_relevant">Not the right kind of role</option>
                <option value="location">Location or work setup</option>
                <option value="salary">Salary</option>
                <option value="seniority">Seniority</option>
                <option value="company">Company preference</option>
                <option value="duplicate">Duplicate</option>
                <option value="closed">Job is closed</option>
                <option value="other">Other</option>
              </select>
            </label>
            <label>
              Note (optional)
              <textarea value={skipNote} onChange={(event) => setSkipNote(event.target.value)} maxLength={500} placeholder="A short note helps you remember the decision" />
            </label>
            <button
              className="button secondary"
              type="button"
              disabled={Boolean(busy) || !skipReason}
              onClick={() => onAction(buildOpportunityActionPayload('mark_skipped', {
                opportunityId: row.opportunity_id,
                decisionReason: skipReason,
                decisionNote: skipNote,
              }))}
            >
              {busy === 'mark_skipped' ? 'Closing…' : 'Close role'}
            </button>
          </div>
        </details>
      </section>

      {canLogApplication ? (
        <section className="detailSection applicationLogForm">
          <h3>Record a manual application</h3>
          <p className="muted small">Use this after you submit on the employer’s website. The dashboard never submits for you.</p>
          <label>
            Application link
            <input value={applicationUrl} onChange={(event) => setApplicationUrl(event.target.value)} placeholder="https://…" />
          </label>
          <label>
            Notes
            <textarea value={applicationNotes} onChange={(event) => setApplicationNotes(event.target.value)} maxLength={1000} placeholder="What you tailored, contact name, or anything to remember" />
          </label>
          <button
            className="button"
            disabled={Boolean(busy) || !safeExternalHttpUrl(applicationUrl)}
            onClick={() => onAction(buildOpportunityActionPayload('log_application', {
              opportunityId: row.opportunity_id,
              applicationUrl,
              applicationNotes,
            }))}
            type="button"
          >
            {busy === 'log_application' ? 'Saving…' : 'Log application'}
          </button>
        </section>
      ) : null}

      {applications.length ? (
        <section className="detailSection outcomeWorkspace">
          <h3>Application outcome</h3>
          <div className="applicationRecord">
            <strong>{humanize(applications[0].outcome || 'applied')}</strong>
            <span>Submitted {applications[0].date_iso || 'date not recorded'}</span>
            {applications[0].notes ? <p>{applications[0].notes}</p> : null}
          </div>
          <div className="outcomeControls">
            <label>
              New outcome
              <select value={outcome} onChange={(event) => setOutcome(event.target.value)}>
                <option value="screening">Screening</option>
                <option value="interview">Interview</option>
                <option value="offer">Offer</option>
                <option value="rejected">Rejected</option>
                <option value="withdrawn">Withdrawn</option>
              </select>
            </label>
            <button
              className="button secondary"
              disabled={Boolean(busy)}
              onClick={() => onAction(buildOpportunityActionPayload('update_application_outcome', {
                opportunityId: row.opportunity_id,
                applicationOutcome: outcome,
              }))}
              type="button"
            >
              Save outcome
            </button>
          </div>
        </section>
      ) : null}

      <details className="detailDisclosure">
        <summary>Job description</summary>
        <div className="jobDescription">{row.description || 'No description recorded.'}</div>
      </details>

      <details className="detailDisclosure">
        <summary>Match evidence and technical details</summary>
        <div className="detailDisclosureBody">
          <div className="detailGrid">
            <DetailItem label="Fit score" value={formatScore(row.match?.fit_score ?? row.match?.score)} />
            <DetailItem label="CV score" value={formatScore(row.match?.cv_score)} />
            <DetailItem label="Role family" value={humanize(row.match?.role_track || 'not assigned')} />
            <DetailItem label="Location" value={row.eligibility_reason || eligibilityLabel(row.location_eligibility)} />
            <DetailItem label="Salary" value={row.salary_text || 'Not stated'} />
            <DetailItem label="Deadline" value={row.deadline || 'Not stated'} />
            <DetailItem label="Live status" value={humanize(row.live_status)} />
            <DetailItem label="Last checked" value={row.live_checked_at || 'Not checked'} />
          </div>
          <p className="muted small"><strong>Keyword gaps:</strong> {row.match?.missing_keywords?.join(', ') || 'None recorded.'}</p>
        </div>
      </details>

      {history.length ? (
        <details className="detailDisclosure">
          <summary>Action history ({history.length})</summary>
          <div className="historyList detailDisclosureBody">
            {history.map((item, index) => (
              <div className="historyItem" key={`${item.created_at}-${item.action_type}-${index}`}>
                <strong>{humanize(item.action_type)}</strong>
                <span>{humanize(item.old_status)} → {humanize(item.new_status)}</span>
                <span className="muted small">{item.created_at}</span>
              </div>
            ))}
          </div>
        </details>
      ) : null}
    </aside>
  )
}

function DetailState({ title, message, error = false }: { title: string; message: string; error?: boolean }) {
  return <aside className="detailPanel"><h2>{title}</h2><p className={error ? 'errorText' : 'muted'}>{message}</p></aside>
}

function ChecklistItem({ done, label }: { done: boolean; label: string }) {
  return <div className={done ? 'done' : ''}><span aria-hidden="true">{done ? '✓' : '○'}</span><strong>{label}</strong></div>
}

function RiskLine({ kind, flags }: { kind: 'blocker' | 'warning'; flags: string[] }) {
  return (
    <div className={`riskSummary ${kind}`}>
      <strong>{kind === 'blocker' ? 'Blocked' : 'Check before continuing'}</strong>
      <span>{flags.map(humanize).join(' · ')}</span>
    </div>
  )
}

function detailRisk(row: OpportunityRow) {
  const blockers = row.risk?.blockers || row.evidence.blockers || []
  const warnings = row.risk?.warnings || row.evidence.warnings || []
  return { blockers, warnings }
}

function primaryActionFor(row: OpportunityRow, blockers: string[]): {
  label: string
  detail: string
  action?: OpportunityActionName
  buttonLabel?: string
  disabled?: boolean
} {
  if (blockers.length) {
    return {
      label: 'Close this role unless the evidence is wrong',
      detail: 'A location, role-family, duplicate, or safety check blocks this opportunity. Choose a reason in the close section below.',
    }
  }
  if (row.status === 'skipped' || row.status === 'expired') {
    return { label: 'No action needed', detail: 'This role is in the closed archive.' }
  }
  if (row.status === 'applied' || row.status === 'follow_up') {
    return { label: 'Update the outcome', detail: 'Record a reply, interview, offer, or rejection below.' }
  }
  if (row.status === 'apply_ready' && !row.pack) {
    return {
      label: 'Prepare the application pack',
      detail: 'The role is shortlisted. Build the local pack, then apply manually.',
      action: 'generate_pack',
      buttonLabel: 'Generate pack',
    }
  }
  if (row.status === 'apply_ready' && row.pack) {
    return { label: 'Apply manually', detail: 'Open the job, submit it yourself, then record the application below.' }
  }
  return {
    label: 'Shortlist or close',
    detail: 'Read the match reason and source, then make one decision.',
    action: 'mark_apply_ready',
    buttonLabel: 'Shortlist role',
  }
}

function ActionButton({
  action,
  label,
  row,
  busy,
  disabled,
  onAction,
}: {
  action: OpportunityActionName
  label: string
  row: OpportunityRow
  busy: string | null
  disabled?: boolean
  onAction: (payload: OpportunityActionPayload) => void
}) {
  return (
    <button
      className="button secondary"
      disabled={Boolean(busy) || disabled}
      onClick={() => onAction(buildOpportunityActionPayload(action, { opportunityId: row.opportunity_id }))}
      type="button"
    >
      {label}
    </button>
  )
}

export function uniqueOptions(values: Array<string | undefined>) {
  return Array.from(new Set(values.map((value) => value || '').filter(Boolean))).sort()
}

export function FilterSelect({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (value: string) => void }) {
  return (
    <label>
      {label}
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="all">All</option>
        {options.map((option) => <option key={option} value={option}>{humanize(option)}</option>)}
      </select>
    </label>
  )
}

function DetailItem({ label, value }: { label: string; value: string }) {
  return <div className="detailItem"><span>{label}</span><strong>{value}</strong></div>
}

function nextActionLabel(value: string) {
  const labels: Record<string, string> = {
    apply_manual: 'Apply manually',
    contact_recruiter: 'Contact recruiter',
    follow_up: 'Follow up',
    make_pack: 'Prepare pack',
    review: 'Review evidence',
    skip: 'Close role',
    tailor_cv: 'Choose or tailor CV',
    wait: 'No action',
  }
  return labels[value] || humanize(value)
}

function eligibilityLabel(value?: string) {
  const labels: Record<string, string> = {
    eligible_vilnius: 'Vilnius fit',
    eligible_lt_remote: 'Lithuania remote',
    eligible_eu_remote: 'EU remote',
    verify_remote: 'Confirm remote eligibility',
    ineligible: 'Location blocked',
  }
  return labels[value || ''] || 'Location not confirmed'
}

function humanize(value: string) {
  return value.replaceAll('_', ' ').replaceAll('-', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function formatScore(value: number | string | undefined | null) {
  if (typeof value === 'number') return value.toFixed(1)
  if (typeof value === 'string' && value) return value
  return '—'
}

export function ActionNotice({
  result,
  busy,
  onUndo,
  onApplySuggestion,
}: {
  result: OpportunityActionResult | { error: string }
  busy: string | null
  onUndo: (opportunityId: string) => void
  onApplySuggestion: (suggestion: NonNullable<OpportunityActionResult['preference_suggestion']>) => void
}) {
  if ('error' in result) return <div className="banner section">{result.error}</div>
  let message = 'Saved.'
  if (result.pack_id) message = 'Application pack is ready.'
  if (result.application_logged) message = 'Application recorded. Follow-up tracking is now active.'
  if (result.application_updated) message = `Outcome updated to ${humanize(result.outcome || '')}.`
  if (result.undone_action) message = `Undone. Status restored to ${humanize(result.restored_status || '')}.`
  if (result.preference_updated) message = 'Search preference updated. Future queues will use it.'
  return (
    <div className="noticeBanner section actionNotice">
      <span>{message}</span>
      <div className="buttonRow">
        {result.can_undo && result.opportunity_id ? (
          <button className="button secondary" type="button" disabled={Boolean(busy)} onClick={() => onUndo(result.opportunity_id!)}>Undo</button>
        ) : null}
        {result.preference_suggestion ? (
          <button className="button secondary" type="button" disabled={Boolean(busy)} onClick={() => onApplySuggestion(result.preference_suggestion!)}>
            {result.preference_suggestion.label}
          </button>
        ) : null}
      </div>
    </div>
  )
}
