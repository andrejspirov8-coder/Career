import { runPythonHelper } from './server/python-bridge'

const helperTimeoutMs = 20_000
const runIdPattern = /^run_[a-f0-9]{32}$/
const scheduleTimePattern = /^(?:[01]\d|2[0-3]):[0-5]\d$/

export type AutomationKind = 'daily_search' | 'cv_build'
export type AutomationStatus =
  | 'queued'
  | 'running'
  | 'cancel_requested'
  | 'succeeded'
  | 'partial'
  | 'failed'
  | 'cancelled'

export type DailySearchJob = {
  opportunity_id?: string
  title?: string
  company?: string
  location?: string
  source?: string
  source_url?: string
  recommended_cv_variant?: string
  fit_score?: number
  next_action?: string
}

export type AutomationRun = {
  run_id: string
  kind: AutomationKind
  status: AutomationStatus
  trigger_source: string
  requested_at: string
  scheduled_for?: string | null
  started_at?: string | null
  finished_at?: string | null
  heartbeat_at?: string | null
  attempt: number
  parent_run_id?: string | null
  phase: string
  progress: number
  result: {
    partial?: boolean
    discovered?: number
    matched?: number
    shown_count?: number
    omitted_count?: number
    source_issues?: Array<{ source?: string; kind?: string; message?: string }>
    new_live_jobs?: DailySearchJob[]
    fresh_live_matches?: DailySearchJob[]
    review_queue?: Record<string, number>
    pdf_count?: number
    pdfs?: Array<{ filename: string; size_bytes: number; updated_at: string }>
    [key: string]: unknown
  }
  error: string
  stdout?: string
  stderr?: string
}

export type AutomationOverview = {
  schema: 'career_automation_overview_v1'
  generated_at: string
  settings: {
    schedule_enabled: boolean
    schedule_time: string
    timezone: string
    updated_at: string
  }
  worker: {
    online: boolean
    status: string
    mode?: string
    started_at?: string
    heartbeat_at?: string
    age_seconds?: number
  }
  counts: Record<AutomationStatus, number>
  active_runs: AutomationRun[]
  recent_runs: AutomationRun[]
  source_health: {
    overall_status: 'healthy' | 'stale' | 'attention' | 'failed' | 'not_run'
    last_checked_at?: string | null
    age_hours?: number | null
    message: string
    sources: Array<{
      source: string
      status: 'healthy' | 'stale' | 'attention' | 'failed'
      raw_status: string
      complete: boolean
      item_count: number
      duration_ms: number
      message: string
    }>
  }
  available_actions: AutomationKind[]
  safety: {
    scheduled_linkedin_enabled: false
    live_linkedin_dispatch_enabled: false
    message: string
  }
}

function runHelper<T>(args: string[]): Promise<T> {
  return runPythonHelper<T>('automation', args, {
    timeoutMs: helperTimeoutMs,
    errorLabel: 'Automation helper',
  })
}

export function isAutomationKind(value: unknown): value is AutomationKind {
  return value === 'daily_search' || value === 'cv_build'
}

export function isAutomationRunId(value: unknown): value is string {
  return typeof value === 'string' && runIdPattern.test(value)
}

export function isScheduleTime(value: unknown): value is string {
  return typeof value === 'string' && scheduleTimePattern.test(value)
}

export async function getAutomationOverview(): Promise<AutomationOverview> {
  return runHelper<AutomationOverview>(['overview', '--limit', '30'])
}

export async function getAutomationRun(runId: string): Promise<AutomationRun> {
  if (!isAutomationRunId(runId)) throw new Error('Invalid automation run id.')
  return runHelper<AutomationRun>(['detail', '--run-id', runId])
}

export async function startAutomationRun(kind: AutomationKind): Promise<{ run: AutomationRun; created: boolean }> {
  if (!isAutomationKind(kind)) throw new Error('Unsupported automation action.')
  const result = await runHelper<{ run: AutomationRun; created: boolean }>([
    'enqueue',
    '--kind',
    kind,
    '--trigger',
    'dashboard',
    '--spawn-worker',
  ])
  return { run: result.run, created: result.created }
}

export async function cancelAutomationRun(runId: string): Promise<{ run: AutomationRun }> {
  if (!isAutomationRunId(runId)) throw new Error('Invalid automation run id.')
  return runHelper<{ run: AutomationRun }>(['cancel', '--run-id', runId])
}

export async function retryAutomationRun(runId: string): Promise<{ run: AutomationRun; created: boolean }> {
  if (!isAutomationRunId(runId)) throw new Error('Invalid automation run id.')
  const result = await runHelper<{ run: AutomationRun; created: boolean }>([
    'retry',
    '--run-id',
    runId,
    '--spawn-worker',
  ])
  return { run: result.run, created: result.created }
}

export async function saveAutomationSchedule(input: {
  enabled: boolean
  scheduleTime: string
  timezone: string
}): Promise<AutomationOverview['settings']> {
  if (!isScheduleTime(input.scheduleTime)) throw new Error('Schedule time must use HH:MM.')
  if (input.timezone !== 'Europe/Vilnius') throw new Error('Unsupported schedule timezone.')
  return runHelper<AutomationOverview['settings']>([
    'set-schedule',
    '--enabled',
    input.enabled ? 'true' : 'false',
    '--time',
    input.scheduleTime,
    '--timezone',
    input.timezone,
  ])
}
