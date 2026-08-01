import { createHash } from 'node:crypto'

import { getApplicationWorkspaceOverview } from './application-data'
import type { ApplicationWorkspaceOverview } from './application-types'
import { getAutomationOverview } from './automation-data'
import type { AutomationOverview, AutomationRun } from './automation-data'
import { getOpportunityOverview } from './opportunity-data'
import type { OpportunityOverview } from './opportunity-data'
import type {
  NotificationActionInput,
  NotificationCandidate,
  NotificationIndividualAction,
  NotificationOverview,
  NotificationScope,
} from './notification-types'
import { runPythonHelper } from './server/python-bridge'

const notificationIdPattern = /^notification_[a-f0-9]{32}$/
const terminalStatuses = new Set(['succeeded', 'partial', 'failed'])
const maxHelperOutputBytes = 4 * 1024 * 1024
const helperTimeoutMs = 30_000
const oneDayMs = 86_400_000

type NotificationInputs = {
  automation?: AutomationOverview | null
  applications?: ApplicationWorkspaceOverview | null
  opportunities?: OpportunityOverview | null
  now?: Date
}

let overviewCache: { expiresAt: number; promise: Promise<NotificationOverview> } | null = null

function bounded(value: unknown, fallback: string, maxLength: number): string {
  const text = typeof value === 'string' ? value.trim() : ''
  return (text || fallback).slice(0, maxLength)
}

function safeIso(value: unknown, fallback: Date): string {
  const parsed = typeof value === 'string' ? new Date(value) : fallback
  return Number.isNaN(parsed.getTime()) ? fallback.toISOString() : parsed.toISOString()
}

function notificationId(key: string): string {
  return `notification_${createHash('sha256').update(key).digest('hex').slice(0, 32)}`
}

function localDate(value: Date): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Europe/Vilnius',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(value)
}

function localTimeMinutes(value: Date): number {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Europe/Vilnius',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(value)
  const hour = Number(parts.find((part) => part.type === 'hour')?.value || 0)
  const minute = Number(parts.find((part) => part.type === 'minute')?.value || 0)
  return hour * 60 + minute
}

function daysFromLocalToday(date: string, now: Date): number {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return Number.POSITIVE_INFINITY
  return Math.floor((Date.parse(`${date}T00:00:00Z`) - Date.parse(`${localDate(now)}T00:00:00Z`)) / oneDayMs)
}

function runTitle(run: AutomationRun): string {
  const catchUp = run.trigger_source === 'schedule_catch_up'
  if (run.kind === 'cv_build') {
    if (run.status === 'succeeded') return 'CV rebuild finished'
    if (run.status === 'partial') return 'CV rebuild needs a quick check'
    return 'CV rebuild failed'
  }
  if (catchUp && run.status === 'succeeded') return 'Morning search caught up after wake'
  if (catchUp && run.status === 'partial') return 'Catch-up search needs a quick check'
  if (run.status === 'succeeded') return 'Daily search finished'
  if (run.status === 'partial') return 'Daily search needs a quick check'
  return 'Daily search failed'
}

function runBody(run: AutomationRun): string {
  if (run.status === 'failed') return 'Open Automation to review the safe error and retry.'
  if (run.status === 'partial') return 'Available results were kept, but at least one source needs attention.'
  if (run.kind === 'cv_build') return `${Number(run.result.pdf_count || 0)} CV PDFs were checked.`
  const count = Number(run.result.shown_count || run.result.matched || 0)
  const suffix = run.trigger_source === 'schedule_catch_up' ? ' The Mac resumed after the planned start time.' : ''
  return `${count} ${count === 1 ? 'role is' : 'roles are'} ready to review.${suffix}`
}

function automationCandidates(automation: AutomationOverview, now: Date): NotificationCandidate[] {
  const candidates: NotificationCandidate[] = []
  for (const run of automation.recent_runs.slice(0, 30)) {
    if (!terminalStatuses.has(run.status)) continue
    candidates.push({
      notification_id: notificationId(`automation:${run.run_id}`),
      scope: 'automation',
      category: 'automation',
      kind: 'automation_completed',
      priority: run.status === 'succeeded' ? 'info' : 'attention',
      lifecycle: 'event',
      title: runTitle(run),
      body: runBody(run),
      href: `/automation?run=${encodeURIComponent(run.run_id)}`,
      occurred_at: safeIso(run.finished_at || run.requested_at, now),
      source_updated_at: safeIso(run.finished_at || run.requested_at, now),
      desktop_eligible: true,
    })
  }

  if (automation.source_health.overall_status !== 'healthy' && automation.source_health.overall_status !== 'not_run') {
    const checkedAt = safeIso(automation.source_health.last_checked_at, now)
    candidates.push({
      notification_id: notificationId(`source-health:${automation.source_health.overall_status}:${checkedAt}`),
      scope: 'automation',
      category: 'system',
      kind: 'source_health',
      priority: automation.source_health.overall_status === 'failed' ? 'urgent' : 'attention',
      lifecycle: 'condition',
      title: automation.source_health.overall_status === 'failed' ? 'A job source failed' : 'Job sources need attention',
      body: bounded(automation.source_health.message, 'Open Automation to review source health.', 500),
      href: '/automation',
      occurred_at: checkedAt,
      source_updated_at: checkedAt,
      desktop_eligible: true,
    })
  }

  if (automation.settings.schedule_enabled && !automation.worker.online) {
    const [hour, minute] = automation.settings.schedule_time.split(':').map(Number)
    const scheduledMinutes = hour * 60 + minute
    const today = localDate(now)
    const runs = [...automation.active_runs, ...automation.recent_runs]
    const hasTodaySearch = runs.some((run) => (
      run.kind === 'daily_search' && localDate(new Date(run.requested_at)) === today
    ))
    if (!hasTodaySearch && localTimeMinutes(now) >= scheduledMinutes + 30) {
      candidates.push({
        notification_id: notificationId(`schedule-missed:${today}`),
        scope: 'automation',
        category: 'system',
        kind: 'schedule_missed',
        priority: 'urgent',
        lifecycle: 'condition',
        title: 'Morning search has not started',
        body: 'The scheduled time passed while the worker was offline. Open Automation to start one safe catch-up run.',
        href: '/automation',
        occurred_at: now.toISOString(),
        source_updated_at: now.toISOString(),
        desktop_eligible: true,
      })
    }
  }
  return candidates
}

function opportunityCandidates(opportunities: OpportunityOverview, now: Date): NotificationCandidate[] {
  const rowsById = new Map(opportunities.queues.all.map((row) => [row.opportunity_id, row]))
  const dailyIds = opportunities.queues.saved_views.daily_queue?.length
    ? opportunities.queues.saved_views.daily_queue
    : opportunities.queues.saved_views.top_5_today || []
  return dailyIds.slice(0, 5).flatMap((opportunityId) => {
    const row = rowsById.get(opportunityId)
    if (!row) return []
    const score = Number(row.match?.fit_score ?? row.match?.score ?? 0)
    const title = bounded(row.title, 'Untitled role', 120)
    const company = bounded(row.company, 'Unknown company', 100)
    const occurredAt = safeIso(row.first_seen_at || row.source_updated_at, now)
    return [{
      notification_id: notificationId(`strong-role:${row.opportunity_id}:${row.first_seen_at || ''}`),
      scope: 'opportunity' as const,
      category: 'opportunity' as const,
      kind: 'strong_role' as const,
      priority: 'attention' as const,
      lifecycle: 'condition' as const,
      title: 'Strong role ready to review',
      body: `${title} at ${company}${score ? ` · match ${score.toFixed(1)}` : ''}.`,
      href: `/opportunities?opportunity=${encodeURIComponent(row.opportunity_id)}`,
      occurred_at: occurredAt,
      source_updated_at: safeIso(row.source_updated_at || row.first_seen_at, now),
      desktop_eligible: true,
    }]
  })
}

function applicationCandidates(applications: ApplicationWorkspaceOverview, now: Date): NotificationCandidate[] {
  const candidates: NotificationCandidate[] = []
  for (const row of applications.rows) {
    const role = bounded(row.title, 'Untitled role', 120)
    const company = bounded(row.company, 'Unknown company', 100)
    const href = `/applications?opportunity=${encodeURIComponent(row.opportunity_id)}`
    const sourceTime = safeIso(
      row.updated_at || (row.reminder_date || row.deadline_date ? `${row.reminder_date || row.deadline_date}T00:00:00Z` : ''),
      now,
    )
    const deadlineDays = daysFromLocalToday(row.deadline_date, now)
    if (deadlineDays >= -14 && deadlineDays <= 7) {
      const title = deadlineDays < 0
        ? 'Application deadline has passed'
        : deadlineDays === 0
          ? 'Application deadline is today'
          : deadlineDays === 1
            ? 'Application deadline is tomorrow'
            : `Application deadline in ${deadlineDays} days`
      candidates.push({
        notification_id: notificationId(`deadline:${row.opportunity_id}:${row.deadline_date}`),
        scope: 'application',
        category: 'application',
        kind: 'application_deadline',
        priority: deadlineDays <= 1 ? 'urgent' : 'attention',
        lifecycle: 'condition',
        title,
        body: `${role} at ${company}. Review the application plan before the deadline.`,
        href,
        occurred_at: sourceTime,
        source_updated_at: sourceTime,
        desktop_eligible: true,
      })
    }

    const reminderDays = daysFromLocalToday(row.reminder_date, now)
    if (reminderDays >= -30 && reminderDays <= 0) {
      candidates.push({
        notification_id: notificationId(`follow-up:${row.opportunity_id}:${row.reminder_date}`),
        scope: 'application',
        category: 'application',
        kind: 'follow_up_due',
        priority: reminderDays < 0 ? 'urgent' : 'attention',
        lifecycle: 'condition',
        title: reminderDays < 0 ? 'Application follow-up is overdue' : 'Application follow-up is due',
        body: `${role} at ${company}. Open Applications to review the next step and draft.`,
        href,
        occurred_at: sourceTime,
        source_updated_at: sourceTime,
        desktop_eligible: true,
      })
    } else if (row.stage === 'follow_up' && !row.reminder_date) {
      candidates.push({
        notification_id: notificationId(`follow-up-stage:${row.opportunity_id}`),
        scope: 'application',
        category: 'application',
        kind: 'follow_up_due',
        priority: 'attention',
        lifecycle: 'condition',
        title: 'Application follow-up is waiting',
        body: `${role} at ${company}. Add a reminder date or record the latest outcome.`,
        href,
        occurred_at: sourceTime,
        source_updated_at: sourceTime,
        desktop_eligible: true,
      })
    }
  }
  return candidates
}

export function createNotificationCandidates({
  automation,
  applications,
  opportunities,
  now = new Date(),
}: NotificationInputs): NotificationCandidate[] {
  return [
    ...(automation ? automationCandidates(automation, now) : []),
    ...(opportunities ? opportunityCandidates(opportunities, now) : []),
    ...(applications ? applicationCandidates(applications, now) : []),
  ].slice(0, 200)
}

function runHelper<T>(command: 'sync' | 'action', input: unknown): Promise<T> {
  return runPythonHelper<T>('notifications', [command], {
    input,
    timeoutMs: helperTimeoutMs,
    maxOutputBytes: maxHelperOutputBytes,
    errorLabel: 'Notification helper',
  })
}

async function refreshNotificationOverview(): Promise<NotificationOverview> {
  const [automationResult, opportunityResult] = await Promise.allSettled([
    getAutomationOverview(),
    getOpportunityOverview(),
  ])
  const automation = automationResult.status === 'fulfilled' ? automationResult.value : null
  const opportunities = opportunityResult.status === 'fulfilled' && !opportunityResult.value.helperError
    ? opportunityResult.value
    : null
  let applications: ApplicationWorkspaceOverview | null = null
  if (opportunities) {
    try {
      applications = await getApplicationWorkspaceOverview(opportunities)
    } catch {
      applications = null
    }
  }
  const syncedScopes: NotificationScope[] = []
  if (automation) syncedScopes.push('automation')
  if (opportunities) syncedScopes.push('opportunity')
  if (applications) syncedScopes.push('application')
  return runHelper<NotificationOverview>('sync', {
    candidates: createNotificationCandidates({ automation, applications, opportunities }),
    synced_scopes: syncedScopes,
  })
}

export function getNotificationOverview({ force = false }: { force?: boolean } = {}): Promise<NotificationOverview> {
  const now = Date.now()
  if (!force && overviewCache && overviewCache.expiresAt > now) return overviewCache.promise
  const promise = refreshNotificationOverview().catch((error) => {
    overviewCache = null
    throw error
  })
  overviewCache = { expiresAt: now + 5_000, promise }
  return promise
}

export function isNotificationId(value: unknown): value is string {
  return typeof value === 'string' && notificationIdPattern.test(value)
}

export function isNotificationIndividualAction(value: unknown): value is NotificationIndividualAction {
  return ['read', 'unread', 'dismiss', 'restore', 'snooze_day', 'snooze_week', 'clear_snooze'].includes(String(value))
}

export async function performNotificationAction(input: NotificationActionInput): Promise<NotificationOverview> {
  overviewCache = null
  const overview = await runHelper<NotificationOverview>('action', input)
  overviewCache = { expiresAt: Date.now() + 1_000, promise: Promise.resolve(overview) }
  return overview
}
