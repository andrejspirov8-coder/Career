import { randomUUID } from 'node:crypto'
import { chmod, mkdir, readFile, realpath, rename, stat, writeFile } from 'node:fs/promises'
import { basename, join, relative, resolve, sep } from 'node:path'

import type {
  ApplicationWorkspaceEntry,
  ApplicationWorkspaceOverview,
  ApplicationWorkspaceRow,
  CoverLetterStatus,
} from './application-types'
import { getOpportunityDetail, getOpportunityOverview, type OpportunityOverview } from './opportunity-data'
import { isOpportunityId } from './opportunity-shared'
import { repositoryRoot as repoRoot } from './server/repository'

const stateRoot = join(repoRoot, 'state')
const workspacePath = join(stateRoot, 'application_workspace.json')
const packsRoot = resolve(repoRoot, 'packs')
const coverLetterStatuses = new Set<CoverLetterStatus>(['not_started', 'draft', 'ready', 'not_needed'])
const packFileLabels = {
  readme: 'Application checklist',
  match_json: 'Match evidence',
  keyword_gaps: 'Keyword gaps',
  job_input: 'Saved job text',
} as const

type StoredWorkspace = {
  schema: 'career_application_workspace_v1'
  entries: Record<string, ApplicationWorkspaceEntry>
}

function cleanText(value: unknown, name: string, maxLength: number): string {
  if (value === undefined || value === null) return ''
  if (typeof value !== 'string' || value.length > maxLength) {
    throw new Error(`${name} must be ${maxLength.toLocaleString()} characters or fewer.`)
  }
  return value.trim()
}

function cleanDate(value: unknown, name: string): string {
  const text = cleanText(value, name, 10)
  if (!text) return ''
  if (!/^\d{4}-\d{2}-\d{2}$/.test(text) || Number.isNaN(Date.parse(`${text}T00:00:00Z`))) {
    throw new Error(`${name} must be a valid date.`)
  }
  return text
}

export function validateApplicationEntry(value: unknown): ApplicationWorkspaceEntry {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Application workspace entry is invalid.')
  }
  const input = value as Record<string, unknown>
  const opportunityId = input.opportunity_id
  if (!isOpportunityId(opportunityId)) throw new Error('A valid opportunity is required.')
  const coverLetterStatus = input.cover_letter_status
  if (typeof coverLetterStatus !== 'string' || !coverLetterStatuses.has(coverLetterStatus as CoverLetterStatus)) {
    throw new Error('Choose a valid cover letter status.')
  }
  return {
    opportunity_id: opportunityId,
    deadline_date: cleanDate(input.deadline_date, 'Deadline'),
    reminder_date: cleanDate(input.reminder_date, 'Reminder'),
    next_step: cleanText(input.next_step, 'Next step', 300),
    contact_name: cleanText(input.contact_name, 'Contact name', 200),
    notes: cleanText(input.notes, 'Notes', 2000),
    cover_letter_status: coverLetterStatus as CoverLetterStatus,
    cover_letter_draft: cleanText(input.cover_letter_draft, 'Cover letter draft', 8000),
    follow_up_draft: cleanText(input.follow_up_draft, 'Follow-up draft', 2000),
    updated_at: typeof input.updated_at === 'string' ? input.updated_at : '',
  }
}

async function loadStoredWorkspace(): Promise<StoredWorkspace> {
  try {
    const parsed = JSON.parse(await readFile(workspacePath, 'utf8')) as unknown
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('Invalid workspace file.')
    const input = parsed as { schema?: unknown; entries?: unknown }
    if (input.schema !== 'career_application_workspace_v1' || !input.entries || typeof input.entries !== 'object' || Array.isArray(input.entries)) {
      throw new Error('Invalid workspace file.')
    }
    const entries = Object.fromEntries(
      Object.entries(input.entries).map(([key, entry]) => [key, validateApplicationEntry(entry)]),
    )
    return { schema: 'career_application_workspace_v1', entries }
  } catch (error) {
    const detail = error as NodeJS.ErrnoException
    if (detail.code === 'ENOENT') return { schema: 'career_application_workspace_v1', entries: {} }
    throw new Error('Application workspace data could not be read.')
  }
}

async function writeStoredWorkspace(workspace: StoredWorkspace) {
  await mkdir(stateRoot, { recursive: true, mode: 0o700 })
  const temporary = `${workspacePath}.${randomUUID()}.tmp`
  await writeFile(temporary, `${JSON.stringify(workspace, null, 2)}\n`, { encoding: 'utf8', mode: 0o600 })
  await rename(temporary, workspacePath)
  await chmod(workspacePath, 0o600)
}

function blankEntry(opportunityId: string, deadline = ''): ApplicationWorkspaceEntry {
  return {
    opportunity_id: opportunityId,
    deadline_date: deadline,
    reminder_date: '',
    next_step: '',
    contact_name: '',
    notes: '',
    cover_letter_status: 'not_started',
    cover_letter_draft: '',
    follow_up_draft: '',
    updated_at: '',
  }
}

function todayIso() {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Vilnius' }).format(new Date())
}

function daysFromToday(date: string) {
  if (!date) return Number.POSITIVE_INFINITY
  const today = Date.parse(`${todayIso()}T00:00:00Z`)
  return Math.floor((Date.parse(`${date}T00:00:00Z`) - today) / 86_400_000)
}

export async function getApplicationWorkspaceOverview(
  opportunityOverview?: OpportunityOverview,
): Promise<ApplicationWorkspaceOverview> {
  const [opportunities, workspace] = await Promise.all([
    opportunityOverview ? Promise.resolve(opportunityOverview) : getOpportunityOverview(),
    loadStoredWorkspace(),
  ])
  const activeStages = new Set(['shortlisted', 'pack_ready', 'applied', 'follow_up'])
  const rows: ApplicationWorkspaceRow[] = opportunities.queues.all
    .filter((row) => activeStages.has(row.stage) || Boolean(workspace.entries[row.opportunity_id]))
    .map((row) => {
      const entry = workspace.entries[row.opportunity_id] || blankEntry(row.opportunity_id, row.deadline || '')
      const variant = row.match?.best_variant || ''
      return {
        ...entry,
        deadline_date: entry.deadline_date || row.deadline || '',
        title: row.title,
        company: row.company,
        location: row.location,
        status: row.status,
        stage: row.stage,
        source_url: row.source_url,
        fit_score: Number(row.match?.fit_score ?? row.match?.score ?? 0),
        cv_variant: variant,
        has_pack: row.has_pack,
        cv_files: variant
          ? {
              visual: `/api/cvs/${encodeURIComponent(variant)}/visual?download=1`,
              ats: `/api/cvs/${encodeURIComponent(variant)}/ats?download=1`,
            }
          : null,
        pack_files: row.has_pack
          ? Object.entries(packFileLabels).map(([key, label]) => ({
              key: key as keyof typeof packFileLabels,
              label,
              url: `/api/applications/files/${encodeURIComponent(row.opportunity_id)}/${key}`,
            }))
          : [],
      }
    })
    .sort((left, right) => {
      const leftDue = Math.min(daysFromToday(left.reminder_date), daysFromToday(left.deadline_date))
      const rightDue = Math.min(daysFromToday(right.reminder_date), daysFromToday(right.deadline_date))
      return leftDue - rightDue || right.fit_score - left.fit_score
    })

  return {
    schema: 'career_application_workspace_v1',
    generated_at: new Date().toISOString(),
    counts: {
      active: rows.length,
      shortlisted: rows.filter((row) => row.stage === 'shortlisted' || row.stage === 'pack_ready').length,
      applied: rows.filter((row) => row.stage === 'applied').length,
      follow_up: rows.filter((row) => row.stage === 'follow_up').length,
      due_next_7_days: rows.filter((row) => {
        const days = daysFromToday(row.deadline_date)
        return days >= 0 && days <= 7
      }).length,
      reminders_due: rows.filter((row) => daysFromToday(row.reminder_date) <= 0).length,
    },
    rows,
  }
}

export async function saveApplicationEntry(value: unknown): Promise<ApplicationWorkspaceEntry> {
  const entry = validateApplicationEntry(value)
  await getOpportunityDetail(entry.opportunity_id)
  const workspace = await loadStoredWorkspace()
  entry.updated_at = new Date().toISOString()
  workspace.entries[entry.opportunity_id] = entry
  await writeStoredWorkspace(workspace)
  return entry
}

function escapeIcs(value: string) {
  return value.replace(/\\/g, '\\\\').replace(/\r?\n/g, '\\n').replace(/,/g, '\\,').replace(/;/g, '\\;')
}

function icsDate(value: string) {
  return value.replaceAll('-', '')
}

export function buildApplicationCalendar(overview: ApplicationWorkspaceOverview): string {
  const events: string[] = []
  for (const row of overview.rows) {
    for (const [kind, date] of [['deadline', row.deadline_date], ['reminder', row.reminder_date]] as const) {
      if (!date) continue
      const summary = kind === 'deadline' ? `Application deadline: ${row.title}` : `Application follow-up: ${row.title}`
      events.push([
        'BEGIN:VEVENT',
        `UID:${escapeIcs(`${row.opportunity_id}-${kind}@career.local`)}`,
        `DTSTAMP:${new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '')}`,
        `DTSTART;VALUE=DATE:${icsDate(date)}`,
        `SUMMARY:${escapeIcs(summary)}`,
        `DESCRIPTION:${escapeIcs([row.company, row.next_step, row.notes].filter(Boolean).join(' — '))}`,
        `URL:http://127.0.0.1:3000/applications?opportunity=${encodeURIComponent(row.opportunity_id)}`,
        'END:VEVENT',
      ].join('\r\n'))
    }
  }
  return ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Career Workspace//Applications//EN', 'CALSCALE:GREGORIAN', ...events, 'END:VCALENDAR', ''].join('\r\n')
}

export async function resolveApplicationPackFile(opportunityId: string, key: string) {
  if (!isOpportunityId(opportunityId) || !(key in packFileLabels)) return null
  const detail = await getOpportunityDetail(opportunityId)
  const path = detail.pack?.files?.[key]
  if (!path) return null
  try {
    const actual = await realpath(path)
    const root = `${await realpath(packsRoot)}${sep}`
    if (!actual.startsWith(root)) return null
    const info = await stat(actual)
    if (!info.isFile() || info.size > 5 * 1024 * 1024) return null
    return {
      path: actual,
      filename: basename(actual),
      relativePath: relative(packsRoot, actual),
      size: info.size,
    }
  } catch {
    return null
  }
}
