'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'

import type {
  ApplicationWorkspaceEntry,
  ApplicationWorkspaceOverview,
  ApplicationWorkspaceRow,
  CoverLetterStatus,
} from '@/lib/application-types'
import type { LocalDraftResult, LocalDraftType, LocalDraftingStatus } from '@/lib/local-drafting-types'
import { safeExternalHttpUrl } from '@/lib/safe-url'
import type { ApiResponse } from '@/lib/api-response'

const coverLetterLabels: Record<CoverLetterStatus, string> = {
  not_started: 'Not started',
  draft: 'Draft in progress',
  ready: 'Ready',
  not_needed: 'Not needed',
}

export default function ApplicationWorkspaceConsole({
  initialOverview,
  initialOpportunity = '',
  draftingStatus,
}: {
  initialOverview: ApplicationWorkspaceOverview
  initialOpportunity?: string
  draftingStatus: LocalDraftingStatus
}) {
  const [overview, setOverview] = useState(initialOverview)
  const [selectedId, setSelectedId] = useState(initialOpportunity)
  const [draft, setDraft] = useState<ApplicationWorkspaceEntry | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const selected = useMemo(
    () => overview.rows.find((row) => row.opportunity_id === selectedId) || overview.rows[0] || null,
    [overview.rows, selectedId],
  )

  useEffect(() => {
    if (!selected) {
      setDraft(null)
      return
    }
    setSelectedId(selected.opportunity_id)
    setDraft({
      opportunity_id: selected.opportunity_id,
      deadline_date: selected.deadline_date,
      reminder_date: selected.reminder_date,
      next_step: selected.next_step,
      contact_name: selected.contact_name,
      notes: selected.notes,
      cover_letter_status: selected.cover_letter_status,
      cover_letter_draft: selected.cover_letter_draft,
      follow_up_draft: selected.follow_up_draft,
      updated_at: selected.updated_at,
    })
  }, [selected])

  useEffect(() => {
    if (!selectedId) return
    const params = new URLSearchParams({ opportunity: selectedId })
    window.history.replaceState(null, '', `${window.location.pathname}?${params.toString()}`)
  }, [selectedId])

  async function refresh() {
    const response = await fetch('/api/applications/overview', { cache: 'no-store' })
    const payload = (await response.json()) as ApiResponse<ApplicationWorkspaceOverview>
    if (!response.ok || !payload.ok || !payload.data) throw new Error(payload.error || 'Workspace could not be refreshed.')
    setOverview(payload.data)
  }

  async function save() {
    if (!draft) return
    setBusy(true)
    setNotice('')
    setError('')
    try {
      const response = await fetch('/api/applications/actions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'save_entry', entry: draft }),
      })
      const payload = (await response.json()) as ApiResponse<ApplicationWorkspaceEntry>
      if (!response.ok || !payload.ok || !payload.data) throw new Error(payload.error || 'Could not save.')
      await refresh()
      setNotice('Application plan saved.')
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : 'Could not save.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <section className="applicationStats" aria-label="Application workspace summary">
        <WorkspaceStat label="Active" value={overview.counts.active} />
        <WorkspaceStat label="Shortlisted" value={overview.counts.shortlisted} />
        <WorkspaceStat label="Applied" value={overview.counts.applied} />
        <WorkspaceStat label="Follow-up" value={overview.counts.follow_up} />
        <WorkspaceStat label="Due in 7 days" value={overview.counts.due_next_7_days} attention={overview.counts.due_next_7_days > 0} />
        <WorkspaceStat label="Reminders due" value={overview.counts.reminders_due} attention={overview.counts.reminders_due > 0} />
      </section>

      {notice ? <div className="noticeBanner section">{notice}</div> : null}
      {error ? <div className="banner section">{error}</div> : null}

      {overview.rows.length ? (
        <section className="applicationLayout">
          <div className="applicationList">
            <div className="applicationListHeading">
              <strong>Application pipeline</strong>
              <small>{overview.rows.length} active {overview.rows.length === 1 ? 'role' : 'roles'}</small>
            </div>
            {overview.rows.map((row) => (
              <button
                className={`applicationListItem ${selected?.opportunity_id === row.opportunity_id ? 'selected' : ''}`}
                key={row.opportunity_id}
                onClick={() => setSelectedId(row.opportunity_id)}
                type="button"
              >
                <span>{humanize(row.stage)}</span>
                <strong>{row.title || row.company || 'Saved role'}</strong>
                <small>{[row.company, row.location].filter(Boolean).join(' · ')}</small>
                <div>
                  {row.deadline_date ? <em>Deadline {row.deadline_date}</em> : null}
                  {row.reminder_date ? <em>Reminder {row.reminder_date}</em> : null}
                </div>
              </button>
            ))}
          </div>

          {selected && draft ? (
            <ApplicationDetail row={selected} draft={draft} setDraft={setDraft} busy={busy} onSave={save} draftingStatus={draftingStatus} />
          ) : null}
        </section>
      ) : (
        <section className="workspacePanel emptyApplicationWorkspace">
          <h2>No active applications yet</h2>
          <p>Shortlist a suitable role first. It will appear here with its recommended CV and preparation files.</p>
          <Link className="buttonLink" href="/opportunities">Open Daily Queue</Link>
        </section>
      )}
    </>
  )
}

function ApplicationDetail({
  row,
  draft,
  setDraft,
  busy,
  onSave,
  draftingStatus,
}: {
  row: ApplicationWorkspaceRow
  draft: ApplicationWorkspaceEntry
  setDraft: (entry: ApplicationWorkspaceEntry) => void
  busy: boolean
  onSave: () => void
  draftingStatus: LocalDraftingStatus
}) {
  const [draftBusy, setDraftBusy] = useState<LocalDraftType | ''>('')
  const [draftNotice, setDraftNotice] = useState('')
  const [draftError, setDraftError] = useState('')
  const [draftInstructions, setDraftInstructions] = useState('')
  const sourceUrl = safeExternalHttpUrl(row.source_url)
  const update = <K extends keyof ApplicationWorkspaceEntry,>(key: K, value: ApplicationWorkspaceEntry[K]) => {
    setDraft({ ...draft, [key]: value })
  }

  async function createLocalDraft(draftType: LocalDraftType) {
    setDraftBusy(draftType)
    setDraftNotice('')
    setDraftError('')
    try {
      const response = await fetch('/api/ai/draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          opportunityId: row.opportunity_id,
          draftType,
          instructions: draftInstructions,
        }),
      })
      const payload = (await response.json()) as ApiResponse<LocalDraftResult>
      if (!response.ok || !payload.ok || !payload.data) throw new Error(payload.error || 'The local draft could not be created.')
      if (draftType === 'cover_letter') {
        setDraft({ ...draft, cover_letter_draft: payload.data.text, cover_letter_status: 'draft' })
      } else {
        setDraft({ ...draft, follow_up_draft: payload.data.text })
      }
      setDraftNotice(`${payload.data.warning} The draft is not saved yet.`)
    } catch (draftingError) {
      setDraftError(draftingError instanceof Error ? draftingError.message : 'The local draft could not be created.')
    } finally {
      setDraftBusy('')
    }
  }
  return (
    <article className="workspacePanel applicationDetailPanel">
      <div className="applicationDetailHeading">
        <div>
          <div className="stageLabel">{humanize(row.stage)}</div>
          <h2>{row.title || row.company || 'Saved role'}</h2>
          <p>{[row.company, row.location].filter(Boolean).join(' · ')}</p>
        </div>
        <div className="buttonRow">
          <Link className="textButton" href={`/opportunities?opportunity=${encodeURIComponent(row.opportunity_id)}`}>Review evidence</Link>
          {sourceUrl ? <a className="textButton" href={sourceUrl} target="_blank" rel="noreferrer noopener">Open job ↗</a> : null}
        </div>
      </div>

      <section className="applicationMaterials">
        <div>
          <span>Chosen CV</span>
          <strong>{row.cv_variant ? humanize(row.cv_variant) : 'Choose in opportunity review'}</strong>
        </div>
        <div className="materialLinks">
          {row.cv_files ? (
            <>
              <a href={row.cv_files.ats}>ATS CV</a>
              <a href={row.cv_files.visual}>Visual CV</a>
            </>
          ) : null}
          {row.pack_files.map((file) => <a href={file.url} key={file.key}>{file.label}</a>)}
          {!row.has_pack ? <Link href={`/opportunities?opportunity=${encodeURIComponent(row.opportunity_id)}`}>Generate application pack</Link> : null}
        </div>
      </section>

      <div className="applicationPlanForm">
        <div className="applicationDateFields">
          <label>
            Application deadline
            <input type="date" value={draft.deadline_date} onChange={(event) => update('deadline_date', event.target.value)} />
          </label>
          <label>
            Follow-up reminder
            <input type="date" value={draft.reminder_date} onChange={(event) => update('reminder_date', event.target.value)} />
          </label>
        </div>
        <label>
          Next step
          <input value={draft.next_step} maxLength={300} onChange={(event) => update('next_step', event.target.value)} placeholder="Tailor summary, request referral, follow up…" />
        </label>
        <label>
          Contact name
          <input value={draft.contact_name} maxLength={200} onChange={(event) => update('contact_name', event.target.value)} placeholder="Hiring manager or recruiter" />
        </label>
        <label>
          Cover letter
          <select value={draft.cover_letter_status} onChange={(event) => update('cover_letter_status', event.target.value as CoverLetterStatus)}>
            {Object.entries(coverLetterLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <section className="localDraftWorkspace" aria-labelledby="local-draft-title">
          <div>
            <span className="eyebrow">Optional local assistant</span>
            <h3 id="local-draft-title">Draft, review, then save</h3>
            <p>{draftingStatus.enabled
              ? draftingStatus.ollama.online
                ? `Uses ${draftingStatus.model} on 127.0.0.1 only.`
                : 'Local drafting is enabled, but Ollama is offline.'
              : 'Local drafting is off. You can still write or paste drafts manually.'}</p>
          </div>
          {draftError ? <div className="banner section" role="alert">{draftError}</div> : null}
          {draftNotice ? <div className="noticeBanner section" role="status">{draftNotice}</div> : null}
          {draftingStatus.enabled ? (
            <>
              <label>
                Optional instructions
                <input maxLength={1000} onChange={(event) => setDraftInstructions(event.target.value)} placeholder="Tone, language, or one truthful point to emphasize" value={draftInstructions} />
              </label>
              <div className="buttonRow">
                <button className="button secondary" disabled={Boolean(draftBusy) || !draftingStatus.ollama.online} onClick={() => createLocalDraft('cover_letter')} type="button">{draftBusy === 'cover_letter' ? 'Drafting locally…' : 'Draft cover letter locally'}</button>
                <button className="button secondary" disabled={Boolean(draftBusy) || !draftingStatus.ollama.online} onClick={() => createLocalDraft('follow_up')} type="button">{draftBusy === 'follow_up' ? 'Drafting locally…' : 'Draft follow-up locally'}</button>
              </div>
            </>
          ) : <Link className="textButton" href="/settings">Review privacy and enable local drafting</Link>}
        </section>
        <label className="applicationDraftField">
          Cover letter draft
          <textarea className="longDraft" value={draft.cover_letter_draft} maxLength={8000} onChange={(event) => update('cover_letter_draft', event.target.value)} placeholder="Write, paste, or create a local draft. Nothing is sent automatically." />
          <small>{draft.cover_letter_draft.length}/8,000</small>
        </label>
        <label className="applicationDraftField">
          Follow-up draft
          <textarea value={draft.follow_up_draft} maxLength={2000} onChange={(event) => update('follow_up_draft', event.target.value)} placeholder="A short message to review and send yourself." />
          <small>{draft.follow_up_draft.length}/2,000</small>
        </label>
        <label>
          Notes
          <textarea value={draft.notes} maxLength={2000} onChange={(event) => update('notes', event.target.value)} placeholder="Tailoring choices, questions, referral details, or interview preparation" />
        </label>
        <button className="button" type="button" disabled={busy} onClick={onSave}>{busy ? 'Saving…' : 'Save application plan'}</button>
      </div>
    </article>
  )
}

function WorkspaceStat({ label, value, attention = false }: { label: string; value: number; attention?: boolean }) {
  return <div className={attention ? 'attention' : ''}><span>{label}</span><strong>{value}</strong></div>
}

function humanize(value: string) {
  return value.replaceAll('_', ' ').replaceAll('-', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}
