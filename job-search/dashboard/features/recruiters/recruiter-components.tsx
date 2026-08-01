'use client'

import {
  buildRecruiterActionPayload,
  rowsForSavedView,
  savedViewOrder,
  type RecruiterActionPayload,
  type SavedViewKey,
} from '../../lib/recruiter-triage'
import { safeLinkedInProfileUrl } from '../../lib/recruiter-links'
import type {
  DashboardActionHistory,
  DashboardRun,
  RecruiterActionResult,
  RecruiterOverview,
  RecruiterQueueRow,
  RecruiterRunActionName,
  ScoreDetails,
} from '../../lib/recruiter-data'

const fallbackCommands: Partial<Record<RecruiterRunActionName, string[]>> = {
  preflight: ['python', '-m', 'career_job_search.recruiters.hiring_network', 'preflight'],
  rank_existing: ['python', '-m', 'career_job_search.recruiters.hiring_network', 'rank'],
}

export function firstNonEmptyView(overview: RecruiterOverview): SavedViewKey {
  return savedViewOrder.find((view) => rowsForSavedView(overview, view).length) ?? 'follow_up'
}

export function uniqueProfileRows(rows: RecruiterQueueRow[]) {
  const seen = new Set<string>()
  const unique: RecruiterQueueRow[] = []
  for (const row of rows) {
    if (seen.has(row.profile_url)) continue
    seen.add(row.profile_url)
    unique.push(row)
  }
  return unique
}

export function uniqueOptions(values: Array<string | undefined>) {
  return Array.from(new Set(values.map((value) => value || '').filter(Boolean))).sort()
}

export function isSentRow(row: RecruiterQueueRow) {
  return ['sent', 'pending', 'accepted', 'replied', 'rejected'].includes(row.status || '')
    || row.score_details?.send_tier === 'sent'
}

export function commandText(overview: RecruiterOverview, action: RecruiterRunActionName) {
  return (overview.safe_actions?.[action] || fallbackCommands[action] || []).join(' ')
}

export function approvalLabel(row: RecruiterQueueRow, sent: boolean) {
  if (sent) return 'sent record'
  if (!row.approval?.approved) return row.approval?.reason || 'not approved'
  const hash = row.approval.note_hash ? ` ${row.approval.note_hash.slice(0, 8)}` : ''
  return `approved${hash}`
}

export function FilterSelect({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (value: string) => void }) {
  return (
    <label>
      {label}
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="all">All</option>
        {options.map((option) => <option key={option} value={option}>{option}</option>)}
      </select>
    </label>
  )
}

export function ProfileDetail({
  row,
  busy,
  draft,
  onDraftChange,
  onAction,
}: {
  row: RecruiterQueueRow | null
  busy: string | null
  draft: string
  onDraftChange: (note: string) => void
  onAction: (payload: RecruiterActionPayload) => void
}) {
  if (!row) {
    return (
      <aside className="detailPanel">
        <h2>Profile Detail</h2>
        <p className="muted">No profile selected.</p>
      </aside>
    )
  }

  const selectedRow = row
  const sent = isSentRow(selectedRow)
  const dirty = draft !== (row.note || '')
  const history = [...(row.action_history || [])].reverse().slice(0, 8)
  const noteQuality = row.note_quality
  const safeProfileUrl = safeLinkedInProfileUrl(row.profile_url)

  async function copyNoteAndRecord() {
    try {
      await navigator.clipboard.writeText(draft)
    } catch {
      // Clipboard availability depends on browser permissions; still record the operator action.
    }
    onAction(buildRecruiterActionPayload('copy_note_recorded', { profileUrl: selectedRow.profile_url, note: draft }))
  }

  return (
    <aside className="detailPanel">
      <div className="detailHeader">
        <div>
          <h2>{row.name || row.profile_url}</h2>
          <p className="muted">{row.headline || row.profile_url}</p>
        </div>
        {safeProfileUrl ? (
          <a href={safeProfileUrl} target="_blank" rel="noreferrer noopener">Open Profile</a>
        ) : (
          <span className="muted small">Profile link unavailable</span>
        )}
      </div>

      <div className="detailGrid">
        <DetailItem label="Company" value={row.company || '-'} />
        <DetailItem label="Location" value={row.location || '-'} />
        <DetailItem label="Persona" value={row.persona || '-'} />
        <DetailItem label="CV" value={row.cv_variant || '-'} />
      </div>

      <section className="detailSection">
        <h3>Score Breakdown</h3>
        <ScoreDetailsGrid details={row.score_details} fallbackScore={row.rank_score} />
      </section>

      <section className="detailSection">
        <h3>Evidence</h3>
        <div className="detailGrid">
          <DetailItem label="Source" value={row.profile_evidence?.source || '-'} />
          <DetailItem label="Company" value={row.profile_evidence?.company?.facts?.join(', ') || row.company || '-'} />
          <DetailItem label="Persona" value={row.profile_evidence?.persona?.evidence?.join(', ') || row.persona || '-'} />
          <DetailItem label="CV Fit" value={row.profile_evidence?.cv_fit?.evidence?.join(', ') || row.cv_variant || '-'} />
          <DetailItem label="Geo" value={row.profile_evidence?.geo?.evidence?.join(', ') || row.location || '-'} />
          <DetailItem label="Confidence" value={formatDetailValue(row.profile_evidence?.confidence)} />
        </div>
      </section>

      <section className="detailSection">
        <h3>Next Action</h3>
        <div className="detailGrid">
          <DetailItem label="Action" value={row.next_action || '-'} />
          <DetailItem label="Reason" value={row.score_explanation?.why_review_or_skip || '-'} />
        </div>
      </section>

      <section className="detailSection">
        <h3>Note Quality</h3>
        <div className="detailGrid">
          <DetailItem label="Status" value={noteQuality?.valid ? 'valid' : 'needs edit'} />
          <DetailItem label="Length" value={`${noteQuality?.length ?? draft.length}/${noteQuality?.max_chars ?? 280}`} />
          <DetailItem label="Issues" value={noteQuality?.issues?.join(', ') || 'none'} />
        </div>
      </section>

      <section className="detailSection">
        <h3>Risk Flags</h3>
        {row.risk_flags?.length ? <div className="riskRow">{row.risk_flags.map((flag) => <span key={flag}>{flag}</span>)}</div> : <p className="muted">None recorded.</p>}
      </section>

      <section className="detailSection">
        <h3>Approval</h3>
        <div className="detailGrid">
          <DetailItem label="Status" value={row.approval?.approved ? 'approved' : row.approval?.reason || 'not approved'} />
          <DetailItem label="Hash" value={row.approval?.note_hash || '-'} />
          <DetailItem label="Operator" value={row.approval?.approved_by || '-'} />
          <DetailItem label="Expires" value={row.approval?.expires_at || '-'} />
        </div>
        {row.approval?.warning ? <p className="muted small">{row.approval.warning}</p> : null}
      </section>

      <section className="detailSection">
        <h3>Current Note</h3>
        {sent ? (
          <div className="readOnlyNote">{row.note || 'No note recorded.'}</div>
        ) : (
          <>
            <textarea
              className="noteBox"
              value={draft}
              maxLength={280}
              onChange={(event) => onDraftChange(event.target.value)}
            />
            <div className="noteMeta">
              <span>{draft.length}/280</span>
              {dirty ? <span>Unsaved edit</span> : null}
            </div>
          </>
        )}
        {row.note_reason ? <p className="muted small">{row.note_reason}</p> : null}
      </section>

      {!sent ? (
        <div className="queueActions">
          <button
            className="button secondary"
            disabled={Boolean(busy) || !dirty}
            onClick={() => onAction(buildRecruiterActionPayload('update_note', { profileUrl: row.profile_url, note: draft }))}
          >
            Save Edited Note
          </button>
          <button
            className="button"
            disabled={Boolean(busy) || !draft.trim()}
            onClick={() => onAction(buildRecruiterActionPayload('approve_note', { profileUrl: row.profile_url, note: draft }))}
          >
            Approve Note
          </button>
          <button
            className="button secondary"
            disabled={Boolean(busy)}
            onClick={() => onAction(buildRecruiterActionPayload('mark_skipped', { profileUrl: row.profile_url }))}
          >
            Mark Skipped
          </button>
          <button
            className="button secondary"
            disabled={Boolean(busy)}
            onClick={() => onAction(buildRecruiterActionPayload('mark_review', { profileUrl: row.profile_url }))}
          >
            Move To Review
          </button>
          <button
            className="button secondary"
            disabled={Boolean(busy) || !draft.trim()}
            onClick={() => void copyNoteAndRecord()}
          >
            Copy Note
          </button>
          <button
            className="button secondary"
            disabled={Boolean(busy) || !draft.trim()}
            onClick={() => onAction(buildRecruiterActionPayload('mark_sent_manual', { profileUrl: row.profile_url, note: draft }))}
          >
            Mark Sent Manually
          </button>
        </div>
      ) : (
        <div className="queueActions followupActions">
          <button className="button secondary" disabled={Boolean(busy)} onClick={() => onAction(buildRecruiterActionPayload('mark_pending', { profileUrl: row.profile_url }))}>Pending</button>
          <button className="button secondary" disabled={Boolean(busy)} onClick={() => onAction(buildRecruiterActionPayload('mark_accepted', { profileUrl: row.profile_url }))}>Accepted</button>
          <button className="button" disabled={Boolean(busy)} onClick={() => onAction(buildRecruiterActionPayload('mark_replied', { profileUrl: row.profile_url }))}>Replied</button>
          <button className="button secondary" disabled={Boolean(busy)} onClick={() => onAction(buildRecruiterActionPayload('mark_rejected', { profileUrl: row.profile_url }))}>No response / closed</button>
          <button className="button secondary" disabled={Boolean(busy)} onClick={() => onAction(buildRecruiterActionPayload('snooze_followup', { profileUrl: row.profile_url }))}>Remind me later</button>
        </div>
      )}

      <section className="detailSection">
        <h3>Action History</h3>
        <ActionHistoryList history={history} />
      </section>
    </aside>
  )
}

function DetailItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="detailItem">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function ScoreDetailsGrid({ details, fallbackScore }: { details?: ScoreDetails; fallbackScore?: RecruiterQueueRow['rank_score'] }) {
  const entries = [
    ['Rank', details?.rank_score ?? fallbackScore],
    ['Primary', details?.primary_score],
    ['Margin', details?.margin_over_second],
    ['Confidence', details?.profile_confidence],
    ['Tier', details?.send_tier],
    ['Decision', details?.decision],
    ['Signals', details?.top_signals?.join(', ')],
  ] as const

  return (
    <div className="detailGrid">
      {entries.map(([label, value]) => (
        <DetailItem key={label} label={label} value={formatDetailValue(value)} />
      ))}
    </div>
  )
}

function ActionHistoryList({ history }: { history: DashboardActionHistory[] }) {
  if (!history.length) return <p className="muted">No dashboard actions recorded.</p>
  return (
    <div className="historyList">
      {history.map((item, index) => (
        <div className="historyItem" key={`${item.timestamp}-${item.action_type}-${index}`}>
          <strong>{item.action_type}</strong>
          <span>{item.old_status} {'->'} {item.new_status}</span>
          <span className="muted small">{item.timestamp} | {item.operator_source}</span>
        </div>
      ))}
    </div>
  )
}

export function RunStatus({ activeRun }: { activeRun: DashboardRun | null }) {
  return (
    <div className="card">
      <h2>Run Status</h2>
      {activeRun ? (
        <div className="runStatus active">
          <strong>{activeRun.action || activeRun.error || 'dashboard action'}</strong>
          <span>{activeRun.started_at || activeRun.path || 'active now'}</span>
        </div>
      ) : (
        <p className="muted">No dashboard action running.</p>
      )}
    </div>
  )
}

export function RecentRuns({ runs }: { runs: DashboardRun[] }) {
  return (
    <div className="card">
      <h2>Recent Runs</h2>
      <div className="list">
        {runs.length ? runs.map((run, index) => (
          <div className="runRow" key={`${run.action || 'run'}-${run.finished_at || index}`}>
            <span>{run.action || 'dashboard action'}</span>
            <span className={run.returncode === 0 ? 'okText' : 'errorText'}>exit {run.returncode ?? '?'}</span>
            <span className="muted small">{run.finished_at || run.started_at || 'n/a'}</span>
          </div>
        )) : <div className="muted">No dashboard runs recorded yet.</div>}
      </div>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return <div className="card"><h3>{label}</h3><div className="kpi">{value}</div></div>
}

export function MetricRow({ left, right }: { left: string; right: string }) {
  return <div className="row"><span>{left}</span><span className="muted">{right}</span></div>
}

export function formatScore(value: RecruiterQueueRow['rank_score']) {
  if (typeof value === 'number') return value.toFixed(1)
  if (typeof value === 'string' && value) return value
  return '-'
}

function formatDetailValue(value: unknown) {
  if (typeof value === 'number') return value.toFixed(2)
  if (typeof value === 'string' && value) return value
  return '-'
}

export function ActionResult({ result }: { result: RecruiterActionResult | { error: string } }) {
  if ('error' in result) {
    return <pre className="actionOutput errorText">{result.error}</pre>
  }
  const output = [result.stdout, result.stderr].filter(Boolean).join('\n\n')
  return (
    <pre className="actionOutput">
      {result.returncode !== undefined ? `exit ${result.returncode}\n` : ''}
      {output || JSON.stringify(result, null, 2)}
    </pre>
  )
}
