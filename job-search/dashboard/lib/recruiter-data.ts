import { runPythonHelper } from './server/python-bridge'

export type ApprovalState = {
  approved: boolean
  reason: string
  note_hash: string
  approved_by?: string
  approval_reason?: string
  approved_at?: string
  expires_at?: string
  warning?: string
  previous_note_hash?: string
}

export type ScoreDetails = {
  rank_score?: number | string | null
  primary_score?: number | string | null
  margin_over_second?: number | string | null
  profile_confidence?: number | string | null
  send_tier?: string
  decision?: string
  top_signals?: string[]
}

export type DashboardActionHistory = {
  action_type: string
  profile_url: string
  timestamp: string
  old_status: string
  new_status: string
  operator_source: string
}

export type ProfileEvidence = {
  source?: string
  company?: { name?: string; facts?: string[] }
  persona?: { label?: string; evidence?: string[] }
  cv_fit?: { variant?: string; score?: number | string | null; evidence?: string[] }
  geo?: { location?: string; evidence?: string[] }
  risk_flags?: string[]
  confidence?: number | string | null
}

export type ScoreExplanation = {
  decision?: string
  send_tier?: string
  why_this_person?: string
  why_this_cv?: string
  why_review_or_skip?: string
}

export type NoteQuality = {
  valid: boolean
  length: number
  max_chars: number
  issues: string[]
}

export type RecruiterQueueRow = {
  profile_url: string
  name: string
  headline: string
  company?: string
  location?: string
  persona: string
  cv_variant: string
  rank_score?: number | string | null
  send_tier?: string
  decision?: string
  risk_flags?: string[]
  note: string
  note_reason?: string
  source_backend?: string
  approval?: ApprovalState
  score_details?: ScoreDetails
  score_explanation?: ScoreExplanation
  profile_evidence?: ProfileEvidence
  next_action?: string
  note_quality?: NoteQuality
  action_history?: DashboardActionHistory[]
  status?: string
}

export type SavedViews = {
  follow_up?: RecruiterQueueRow[]
  ready_to_contact?: RecruiterQueueRow[]
  needs_review: RecruiterQueueRow[]
  auto_send_candidates: RecruiterQueueRow[]
  approved: RecruiterQueueRow[]
  skipped: RecruiterQueueRow[]
  sent: RecruiterQueueRow[]
  sent_archive?: RecruiterQueueRow[]
  risk_flags: RecruiterQueueRow[]
}

export type RecruiterRunActionName = 'preflight' | 'search_rank' | 'rank_existing' | 'dispatch_dry_run'

export type RecruiterOverview = {
  schema: 'recruiter_dashboard_overview_v1'
  generated_at: string
  send_mode?: 'manual' | 'cli_gated' | string
  files: Record<string, string>
  counts: {
    total_ranked: number
    auto_send: number
    queue_review: number
    skipped: number
    approved_notes: number
    sent: number
    accepted: number
    reply: number
    interview: number
    malformed_action_rows: number
  }
  queues: {
    auto_send: RecruiterQueueRow[]
    review: RecruiterQueueRow[]
    skipped: RecruiterQueueRow[]
    sent: RecruiterQueueRow[]
    saved_views?: SavedViews
  }
  metrics: {
    personas: Record<string, { queued: number; sent: number; accepted: number; reply: number; interview: number; accept_rate: number; reply_rate: number }>
    variants: Record<string, { queued: number; sent: number; accepted: number; reply: number; interview: number; accept_rate: number; reply_rate: number }>
    risk_flags: Record<string, number>
  }
  run_state: Record<string, unknown>
  persona_stats: Record<string, unknown>
  active_run?: DashboardRun | null
  recent_runs?: DashboardRun[]
  run_history?: DashboardRun[]
  campaign?: {
    readiness?: {
      ready_for_manual_send?: number
      approvals_valid?: number
      stale_notes?: number
      risky_profiles?: number
      expected_manual_minutes?: number
    }
  }
  risk_stop_state?: {
    stopped: boolean
    reason: string
    signals?: string[]
    failure_rate?: number
    pending_invites?: number
    daily_cap_reached?: boolean
    screen_state?: string
  }
  live_dispatch?: {
    mode: 'manual' | 'cli_gated' | 'cli_only' | string
    message: string
    auto_send_candidates: number
    approved_notes: number
    ready_for_cli_dispatch: boolean
    ready_for_manual_send?: number
  }
  safe_actions?: SafeActionCommands
  helperError?: string
}

export type RecruiterActionName =
  | RecruiterRunActionName
  | 'approve_note'
  | 'update_note'
  | 'mark_skipped'
  | 'mark_review'
  | 'bulk_mark_skipped'
  | 'bulk_mark_review'
  | 'copy_note_recorded'
  | 'mark_sent_manual'
  | 'mark_pending'
  | 'mark_replied'
  | 'mark_accepted'
  | 'mark_rejected'
  | 'snooze_followup'

export type RecruiterActionResult = {
  action?: string
  command?: string[]
  started_at?: string
  finished_at?: string
  returncode?: number
  stdout?: string
  stderr?: string
  approved?: boolean
  updated?: boolean
  reason?: string
  profile_url?: string
  note_hash?: string
  note?: string
}

export type DashboardRun = RecruiterActionResult & {
  error?: string
  path?: string
}

export type SafeActionCommands = Partial<Record<RecruiterRunActionName, string[]>>

function emptyOverview(helperError?: string): RecruiterOverview {
  return {
    schema: 'recruiter_dashboard_overview_v1',
    generated_at: new Date().toISOString(),
    files: {},
    counts: {
      total_ranked: 0,
      auto_send: 0,
      queue_review: 0,
      skipped: 0,
      approved_notes: 0,
      sent: 0,
      accepted: 0,
      reply: 0,
      interview: 0,
      malformed_action_rows: 0,
    },
    queues: {
      auto_send: [],
      review: [],
      skipped: [],
      sent: [],
      saved_views: {
        follow_up: [],
        ready_to_contact: [],
        needs_review: [],
        auto_send_candidates: [],
        approved: [],
        skipped: [],
        sent: [],
        sent_archive: [],
        risk_flags: [],
      },
    },
    metrics: { personas: {}, variants: {}, risk_flags: {} },
    run_state: {},
    persona_stats: {},
    active_run: null,
    recent_runs: [],
    safe_actions: {},
    helperError,
  }
}

async function runHelper(args: string[]) {
  return runPythonHelper<unknown>('recruiters', args, {
    timeoutMs: 30_000,
    errorLabel: 'Recruiter helper',
  })
}

export async function getRecruiterOverview(): Promise<RecruiterOverview> {
  try {
    return (await runHelper(['overview'])) as RecruiterOverview
  } catch (error) {
    const message = error instanceof Error ? error.message : 'unknown helper error'
    return emptyOverview(message)
  }
}

export async function runRecruiterAction(action: RecruiterRunActionName): Promise<RecruiterActionResult> {
  return (await runHelper(['action', '--name', action])) as RecruiterActionResult
}

export async function approveRecruiterNote(profileUrl: string, note: string): Promise<RecruiterActionResult> {
  return (await runHelper(['approve', '--profile-url', profileUrl, '--note', note])) as RecruiterActionResult
}

export async function updateRecruiterNote(profileUrl: string, note: string): Promise<RecruiterActionResult> {
  return (await runHelper(['update-note', '--profile-url', profileUrl, '--note', note])) as RecruiterActionResult
}

export async function markRecruiterSkipped(profileUrl: string): Promise<RecruiterActionResult> {
  return (await runHelper(['mark-skipped', '--profile-url', profileUrl])) as RecruiterActionResult
}

export async function markRecruiterReview(profileUrl: string): Promise<RecruiterActionResult> {
  return (await runHelper(['mark-review', '--profile-url', profileUrl])) as RecruiterActionResult
}

export async function bulkMarkRecruitersSkipped(profileUrls: string[]): Promise<RecruiterActionResult> {
  const profileArgs = profileUrls.flatMap((profileUrl) => ['--profile-url', profileUrl])
  return (await runHelper(['bulk-mark-skipped', ...profileArgs])) as RecruiterActionResult
}

export async function bulkMarkRecruitersReview(profileUrls: string[]): Promise<RecruiterActionResult> {
  const profileArgs = profileUrls.flatMap((profileUrl) => ['--profile-url', profileUrl])
  return (await runHelper(['bulk-mark-review', ...profileArgs])) as RecruiterActionResult
}

export async function recordRecruiterOperatorAction(
  actionType: RecruiterActionName,
  profileUrl: string,
  note = '',
): Promise<RecruiterActionResult> {
  return (await runHelper([
    'operator-action',
    '--action-type',
    actionType,
    '--profile-url',
    profileUrl,
    '--note',
    note,
  ])) as RecruiterActionResult
}
