'use client'

import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'

import type {
  DashboardDevAgentRole,
  DevAgentCheckPreset,
  DevAgentOverview,
  DevAgentProposal,
  DevAgentRun,
  DevAgentStatus,
} from '../../lib/dev-agent-data'

type ApiResponse<T> = { ok?: boolean; data?: T; error?: string }

const activeStatuses = new Set<DevAgentStatus>(['queued', 'snapshotting', 'running', 'local_review', 'verifying'])
const rejectableStatuses = new Set<DevAgentStatus>([
  'ready_for_codex_review',
  'approved',
  'blocked',
  'failed',
  'timed_out',
  'cancelled',
  'stale',
])

function formatDate(value?: string | null): string {
  if (!value) return 'Not yet'
  return new Date(value).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })
}

function statusLabel(status: string): string {
  return status.replaceAll('_', ' ')
}

function shortId(taskId: string): string {
  return taskId.replace('agent_', '').slice(0, 8)
}

function checkSummary(run: DevAgentRun): string {
  const checks = run.status === 'applied' ? run.post_apply_verification : run.verification
  if (!checks.length) return 'No deterministic checks declared'
  const passed = checks.filter((check) => check.status === 'passed').length
  return `${passed}/${checks.length} checks passed`
}

export default function DevAgentConsole({ initialOverview }: { initialOverview: DevAgentOverview }) {
  const [overview, setOverview] = useState(initialOverview)
  const [selectedRunId, setSelectedRunId] = useState(
    initialOverview.active_runs[0]?.task_id || initialOverview.recent_runs[0]?.task_id || '',
  )
  const [selectedDetail, setSelectedDetail] = useState<DevAgentRun | null>(null)
  const [role, setRole] = useState<DashboardDevAgentRole>('explorer')
  const [objective, setObjective] = useState('')
  const [allowedPaths, setAllowedPaths] = useState('.')
  const [verification, setVerification] = useState<DevAgentCheckPreset>('none')
  const [risk, setRisk] = useState<'low' | 'medium'>('low')
  const [contextNotes, setContextNotes] = useState('')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [editingProposalId, setEditingProposalId] = useState('')

  const qualified = Boolean(overview.rollout.qualified_at)

  const refresh = useCallback(async () => {
    const response = await fetch('/api/dev-agents/overview', { cache: 'no-store' })
    const payload = (await response.json()) as ApiResponse<DevAgentOverview>
    if (!response.ok || !payload.ok || !payload.data) {
      throw new Error(payload.error || 'Development-agent status could not be refreshed.')
    }
    setOverview(payload.data)
    setSelectedRunId((current) => current || payload.data?.active_runs[0]?.task_id || payload.data?.recent_runs[0]?.task_id || '')
  }, [])

  const loadRun = useCallback(async (taskId: string) => {
    if (!taskId) return
    const response = await fetch(`/api/dev-agents/runs/${encodeURIComponent(taskId)}`, { cache: 'no-store' })
    const payload = (await response.json()) as ApiResponse<DevAgentRun>
    if (!response.ok || !payload.ok || !payload.data) {
      throw new Error(payload.error || 'Development-agent run could not be loaded.')
    }
    setSelectedDetail(payload.data)
  }, [])

  useEffect(() => {
    if (!selectedRunId) return
    loadRun(selectedRunId).catch(() => undefined)
  }, [loadRun, selectedRunId])

  useEffect(() => {
    const interval = window.setInterval(() => {
      void refresh().then(() => selectedRunId ? loadRun(selectedRunId) : undefined).catch(() => undefined)
    }, overview.active_runs.length ? 3000 : 12000)
    return () => window.clearInterval(interval)
  }, [loadRun, overview.active_runs.length, refresh, selectedRunId])

  const selectedSummary = useMemo(
    () => overview.recent_runs.find((run) => run.task_id === selectedRunId) || overview.active_runs[0] || overview.recent_runs[0],
    [overview, selectedRunId],
  )
  const selectedRun = selectedDetail?.task_id === selectedSummary?.task_id ? selectedDetail : selectedSummary

  async function postAction(body: Record<string, unknown>) {
    const response = await fetch('/api/dev-agents/actions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const payload = (await response.json()) as ApiResponse<{
      run?: DevAgentRun
      proposal?: DevAgentProposal
      autonomy?: DevAgentOverview['autonomy']
      started?: boolean
    }>
    if (!response.ok || !payload.ok || !payload.data) {
      throw new Error(payload.error || 'Development-agent action failed.')
    }
    return payload.data
  }

  async function submitTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy('start')
    setError('')
    setNotice('')
    try {
      const data = await postAction({
        action: editingProposalId ? 'approve_proposal' : 'start',
        proposalId: editingProposalId || undefined,
        objective,
        role,
        allowedPaths: allowedPaths.split(/[\n,]/).map((path) => path.trim()).filter(Boolean),
        verification,
        risk,
        contextNotes,
      })
      if (data.run) {
        setSelectedRunId(data.run.task_id)
        setSelectedDetail(data.run)
      }
      setObjective('')
      setEditingProposalId('')
      setNotice(
        editingProposalId
          ? 'Proposal approved and queued as a typed local task.'
          : role === 'explorer'
            ? 'Read-only exploration was queued locally.'
            : 'Implementation was queued in a disposable worktree.',
      )
      await refresh()
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : 'Task could not be queued.')
    } finally {
      setBusy('')
    }
  }

  async function proposalAction(action: 'reject_proposal', proposalId: string) {
    setBusy(`${action}:${proposalId}`)
    setError('')
    setNotice('')
    try {
      await postAction({ action, proposalId })
      setNotice('Proposal rejected. No model or code change was started.')
      await refresh()
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : 'Proposal action failed.')
    } finally {
      setBusy('')
    }
  }

  async function controlAction(action: 'run_planner' | 'qualify_qwen36' | 'pause_autonomy' | 'resume_autonomy') {
    setBusy(action)
    setError('')
    setNotice('')
    try {
      await postAction({ action })
      setNotice(
        action === 'run_planner'
          ? 'The read-only planner started in the background.'
          : action === 'qualify_qwen36'
            ? 'Qwen 3.6 qualification started in the background.'
            : action === 'pause_autonomy'
              ? 'Documentation and test auto-apply is paused.'
              : 'Auto-apply resumed after the safety thresholds were checked.',
      )
      await refresh()
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : 'Development-agent control failed.')
    } finally {
      setBusy('')
    }
  }

  function editProposal(proposal: DevAgentProposal) {
    setEditingProposalId(proposal.proposal_id)
    setRole('implementer')
    setObjective(proposal.objective)
    setAllowedPaths(proposal.allowed_paths.join('\n'))
    setVerification(proposal.check_preset)
    setRisk(proposal.risk)
    setContextNotes(proposal.evidence.join('\n'))
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  async function changeRun(action: 'cancel' | 'reject' | 'apply', taskId: string) {
    setBusy(`${action}:${taskId}`)
    setError('')
    setNotice('')
    try {
      const data = await postAction({ action, taskId })
      if (data.run) setSelectedDetail(data.run)
      setNotice(
        action === 'cancel'
          ? 'Cancellation requested.'
          : action === 'reject'
            ? 'Run rejected and its registered worktree removed.'
            : 'Approved patch applied without staging or committing.',
      )
      await refresh()
      await loadRun(taskId)
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : 'Run action failed.')
    } finally {
      setBusy('')
    }
  }

  function changeRole(nextRole: DashboardDevAgentRole) {
    setRole(nextRole)
    setAllowedPaths(nextRole === 'explorer' ? '.' : 'tests')
    setVerification(nextRole === 'explorer' ? 'none' : 'python')
  }

  const rolloutPercent = Math.min(
    100,
    Math.round((overview.rollout.safe_applied_runs / Math.max(overview.rollout.required_safe_runs, 1)) * 100),
  )
  const findings = selectedRun?.local_review.findings || []
  const proposedTasks = overview.proposals.filter((proposal) => proposal.status === 'proposed')
  const activeModel = overview.rollout.models.find(
    (model) => model.model === overview.rollout.selected_implementer_model && model.digest === overview.rollout.selected_implementer_digest,
  )

  return (
    <>
      <div className="workspaceHeading devAgentHeading">
        <div>
          <div className="eyebrow">Local engineering</div>
          <h1>Development Agents</h1>
          <p className="muted">Delegate bounded repository work to Ollama, inspect the exact patch, and keep Main Codex as the approval gate.</p>
        </div>
        <div className={`serviceIndicator ${qualified ? 'online' : ''}`}>
          <span aria-hidden="true" />
          <div>
            <strong>{qualified ? 'Local models qualified' : 'Writing locked'}</strong>
            <small>{qualified ? overview.rollout.selected_implementer_model : 'Run doctor and benchmark first'}</small>
          </div>
        </div>
      </div>

      <div className="buttonRow devAgentTopActions">
        <button className="button secondary" disabled={Boolean(busy)} onClick={() => controlAction('run_planner')} type="button">Run read-only planner</button>
        <button className="button secondary" disabled={Boolean(busy)} onClick={() => controlAction('qualify_qwen36')} type="button">Qualify Qwen 3.6</button>
        <button
          className="textButton"
          disabled={Boolean(busy)}
          onClick={() => controlAction(overview.autonomy.auto_apply_enabled ? 'pause_autonomy' : 'resume_autonomy')}
          type="button"
        >
          {overview.autonomy.auto_apply_enabled ? 'Pause auto-apply' : 'Resume auto-apply'}
        </button>
      </div>

      {error ? <div className="banner" role="alert">{error}</div> : null}
      {notice ? <div className="noticeBanner" role="status">{notice}</div> : null}

      <section className="devAgentSafetyBand" aria-label="Development-agent safety status">
        <div><span>Service</span><strong>{overview.service.online ? 'Running locally' : 'Offline'}</strong></div>
        <div><span>Planner</span><strong>Weekdays {overview.service.schedule_time}</strong></div>
        <div><span>Autonomy</span><strong>Tier {overview.autonomy.tier} · {overview.autonomy.auto_apply_enabled ? 'docs/tests auto' : 'review required'}</strong></div>
        <div>
          <span>Local-first pilot</span>
          <strong>{overview.rollout.safe_applied_runs}/{overview.rollout.required_safe_runs} safe runs</strong>
          <i><em style={{ width: `${rolloutPercent}%` }} /></i>
        </div>
      </section>

      <section className="workspacePanel devAgentProposals" aria-labelledby="agent-proposals-title">
        <div className="panelHeading">
          <div>
            <div className="eyebrow">Planner backlog</div>
            <h2 id="agent-proposals-title">Proposed local work</h2>
            <p>{proposedTasks.length} waiting · maximum two approved implementations per weekday</p>
          </div>
          <span className="statusPill">Approval required</span>
        </div>
        {proposedTasks.length ? (
          <div className="devAgentProposalList">
            {proposedTasks.map((proposal) => (
              <article key={proposal.proposal_id}>
                <div>
                  <span>{proposal.priority} · {proposal.category.replaceAll('_', ' ')}</span>
                  <h3>{proposal.objective}</h3>
                  <p>{proposal.evidence.join(' · ')}</p>
                  <small>{proposal.allowed_paths.join(', ')} · {proposal.estimated_files} files / {proposal.estimated_diff_lines} lines</small>
                </div>
                <div className="buttonRow">
                  <button className="button secondary" disabled={Boolean(busy)} onClick={() => editProposal(proposal)} type="button">Review or edit</button>
                  <button className="textButton" disabled={Boolean(busy)} onClick={() => proposalAction('reject_proposal', proposal.proposal_id)} type="button">Reject</button>
                </div>
              </article>
            ))}
          </div>
        ) : <div className="emptyState">No planner proposals are waiting. Run the read-only planner when you want fresh suggestions.</div>}
      </section>

      <section className="workspacePanel devAgentModelStrip" aria-label="Local model rollout">
        <div><span>Active implementer</span><strong>{activeModel?.model || overview.rollout.selected_implementer_model || 'Not qualified'}</strong><small>{activeModel ? activeModel.digest.slice(0, 12) : 'No pinned digest'}</small></div>
        <div><span>Safe streak</span><strong>{overview.rollout.safe_apply_streak}</strong><small>Tier 1 at 10 · Tier 2 at 20</small></div>
        <div><span>First-pass rate</span><strong>{Math.round(overview.autonomy.rolling_first_pass_rate * 100)}%</strong><small>{overview.autonomy.rolling_window}-run window</small></div>
        <div><span>Resource gate</span><strong>{overview.resources.implementer.ok ? 'Ready' : 'Deferred'}</strong><small>{overview.resources.implementer.reason || 'Power, disk and automation checks pass'}</small></div>
      </section>

      <div className="devAgentWorkspace">
        <section className="workspacePanel devAgentLauncher" aria-labelledby="agent-task-title">
          <div className="panelHeading">
            <div>
              <div className="eyebrow">Typed task</div>
              <h2 id="agent-task-title">{editingProposalId ? 'Review planner proposal' : 'Queue local work'}</h2>
              <p>{editingProposalId ? 'Edit the typed objective, paths, and fixed verification preset before approval.' : 'No free-form shell commands, installs, Git actions, or online fallback.'}</p>
            </div>
            <span className="statusPill">Serial queue</span>
          </div>
          <form className="devAgentForm" onSubmit={submitTask}>
            <fieldset>
              <legend>Role</legend>
              <label>
                <input checked={role === 'explorer'} onChange={() => changeRole('explorer')} type="radio" />
                <span><strong>Explorer</strong><small>Read-only repository findings</small></span>
              </label>
              <label className={!qualified ? 'disabled' : ''}>
                <input checked={role === 'implementer'} disabled={!qualified} onChange={() => changeRole('implementer')} type="radio" />
                <span><strong>Implementer</strong><small>{qualified ? 'Writes only in a disposable worktree' : 'Unlocks only after benchmark qualification'}</small></span>
              </label>
            </fieldset>
            <label>
              Objective
              <textarea
                maxLength={2000}
                onChange={(event) => setObjective(event.target.value)}
                placeholder="Example: map the opportunity detail flow and identify one focused test gap."
                required
                rows={4}
                value={objective}
              />
            </label>
            <label>
              Allowed repository paths
              <textarea
                maxLength={1200}
                onChange={(event) => setAllowedPaths(event.target.value)}
                required
                rows={3}
                value={allowedPaths}
              />
              <small>One path per line. Implementers cannot use the whole repository.</small>
            </label>
            <div className="devAgentFormRow">
              <label>
                Verification
                <select onChange={(event) => setVerification(event.target.value as DevAgentCheckPreset)} value={verification}>
                  <option value="none">No test preset</option>
                  <option value="python">Python tests</option>
                  <option value="dashboard">Dashboard tests + typecheck</option>
                  <option value="raycast">Raycast tests + typecheck</option>
                </select>
              </label>
              <label>
                Risk
                <select onChange={(event) => setRisk(event.target.value as 'low' | 'medium')} value={risk}>
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                </select>
              </label>
            </div>
            <details>
              <summary>Optional context for the local model</summary>
              <textarea maxLength={2000} onChange={(event) => setContextNotes(event.target.value)} rows={3} value={contextNotes} />
            </details>
            <button className="button" disabled={busy === 'start'} type="submit">
              {busy === 'start' ? 'Queueing…' : editingProposalId ? 'Approve and queue proposal' : role === 'explorer' ? 'Queue read-only exploration' : 'Queue disposable implementation'}
            </button>
            {editingProposalId ? (
              <button className="textButton" onClick={() => setEditingProposalId('')} type="button">Cancel proposal edit</button>
            ) : null}
          </form>
        </section>

        <section className="workspacePanel devAgentQueue" aria-labelledby="agent-queue-title">
          <div className="panelHeading">
            <div>
              <div className="eyebrow">Serial activity</div>
              <h2 id="agent-queue-title">Run queue</h2>
              <p>{overview.active_runs.length} active · newest first</p>
            </div>
            <button className="textButton" onClick={() => refresh().catch((refreshError) => setError(refreshError.message))} type="button">Refresh</button>
          </div>
          <div className="runList">
            {overview.recent_runs.length ? overview.recent_runs.map((run) => (
              <button
                className={`runListItem ${selectedRun?.task_id === run.task_id ? 'selected' : ''}`}
                key={run.task_id}
                onClick={() => {
                  setSelectedRunId(run.task_id)
                  setSelectedDetail(null)
                }}
                type="button"
              >
                <span className={`statusDot status-${run.status}`} aria-hidden="true" />
                <span className="runListMain">
                  <strong>{run.task.objective || `${run.role} task`}</strong>
                  <small>{formatDate(run.created_at)} · {run.model}</small>
                </span>
                <span className={`statusText status-${run.status}`}>{statusLabel(run.status)}</span>
              </button>
            )) : <div className="emptyState">No local development runs yet. Start with a read-only exploration.</div>}
          </div>
        </section>
      </div>

      <section className="workspacePanel devAgentInspector" aria-labelledby="agent-inspector-title">
        {selectedRun ? (
          <>
            <div className="panelHeading">
              <div>
                <div className="eyebrow">Run {shortId(selectedRun.task_id)}</div>
                <h2 id="agent-inspector-title">{selectedRun.task.objective || `${selectedRun.role} task`}</h2>
                <p>{selectedRun.role} · {selectedRun.model} · attempt {selectedRun.attempt}</p>
              </div>
              <span className={`statusPill status-${selectedRun.status}`}>{statusLabel(selectedRun.status)}</span>
            </div>
            <div className="devAgentInspectorGrid">
              <div className="devAgentRunSummary">
                <div><span>Phase</span><strong>{statusLabel(selectedRun.phase)}</strong></div>
                <div><span>Checks</span><strong>{checkSummary(selectedRun)}</strong></div>
                <div><span>Changed</span><strong>{selectedRun.result.changed_files?.length || 0} files · {selectedRun.result.diff_lines || 0} lines</strong></div>
                <div><span>Patch</span><strong>{selectedRun.patch_sha256 ? selectedRun.patch_sha256.slice(0, 12) : 'Not created'}</strong></div>
                {selectedRun.result.summary ? <p>{selectedRun.result.summary}</p> : null}
                {selectedRun.error ? <div className="inlineWarning">{selectedRun.error}</div> : null}
                {selectedRun.status === 'ready_for_codex_review' ? (
                  <div className="devAgentApprovalNote">Main Codex must review this exact patch hash in the CLI before Apply becomes available.</div>
                ) : null}
                <div className="buttonRow">
                  {activeStatuses.has(selectedRun.status) ? (
                    <button className="button secondary" disabled={Boolean(busy)} onClick={() => changeRun('cancel', selectedRun.task_id)} type="button">Cancel run</button>
                  ) : null}
                  {rejectableStatuses.has(selectedRun.status) ? (
                    <button className="button secondary" disabled={Boolean(busy)} onClick={() => changeRun('reject', selectedRun.task_id)} type="button">Reject and clean up</button>
                  ) : null}
                  {selectedRun.status === 'approved' ? (
                    <button className="button" disabled={Boolean(busy)} onClick={() => changeRun('apply', selectedRun.task_id)} type="button">Apply approved patch</button>
                  ) : null}
                </div>
              </div>
              <div className="devAgentEvidence">
                <section>
                  <h3>Local review</h3>
                  {findings.length ? findings.map((finding, index) => (
                    <div className={`agentFinding severity-${finding.severity}`} key={`${finding.title}-${index}`}>
                      <span>{finding.severity}</span>
                      <strong>{finding.title}</strong>
                      <p>{finding.detail}</p>
                    </div>
                  )) : <p className="muted small">No reviewer findings recorded.</p>}
                </section>
                <section>
                  <h3>Deterministic checks</h3>
                  {(selectedRun.status === 'applied' ? selectedRun.post_apply_verification : selectedRun.verification).length ? (
                    <div className="agentCheckList">
                      {(selectedRun.status === 'applied' ? selectedRun.post_apply_verification : selectedRun.verification).map((check) => (
                        <div key={`${check.name}-${check.cwd}`}><strong>{check.name}</strong><span className={`status-${check.status}`}>{check.status}</span></div>
                      ))}
                    </div>
                  ) : <p className="muted small">Checks have not run yet.</p>}
                </section>
              </div>
            </div>
            {selectedRun.patch_preview ? (
              <details className="devAgentPatch" open>
                <summary>Patch preview{selectedRun.patch_preview_truncated ? ' (truncated)' : ''}</summary>
                <pre>{selectedRun.patch_preview}</pre>
              </details>
            ) : null}
          </>
        ) : <div className="emptyState">Select a run to inspect its model summary, review findings, checks, and patch.</div>}
      </section>
    </>
  )
}
