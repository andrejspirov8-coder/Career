import { runPythonHelper } from './server/python-bridge'

const quickHelperTimeoutMs = 20_000
const applyHelperTimeoutMs = 30 * 60_000
const taskIdPattern = /^agent_[a-f0-9]{32}$/
const proposalIdPattern = /^proposal_[a-f0-9]{32}$/
const relativePathPattern = /^(?:\.|[A-Za-z0-9_@+.-]+(?:\/[A-Za-z0-9_@+.-]+)*)$/

const protectedWritePaths = [
  '.codex',
  '.github',
  '.gitignore',
  'AGENTS.md',
  'SECURITY.md',
  'pyproject.toml',
  'uv.lock',
  'config/local_dev_agents.yaml',
  'tools/local_dev_agents.py',
  'tools/local_dev_agent_models.py',
  'dashboard/lib/dashboard-auth.ts',
  'dashboard/app/api/auth',
  'dashboard/package.json',
  'dashboard/package-lock.json',
  'raycast-job-search-hub/package.json',
  'raycast-job-search-hub/package-lock.json',
  'scripts/verify_release.sh',
  'tools/linkedin',
  'linkedin',
] as const

export type DevAgentRole = 'planner' | 'explorer' | 'implementer' | 'reviewer'
export type DashboardDevAgentRole = Exclude<DevAgentRole, 'planner' | 'reviewer'>
export type DevAgentRisk = 'low' | 'medium'
export type DevAgentCheckPreset = 'none' | 'python' | 'dashboard' | 'raycast'
export type DevAgentStatus =
  | 'queued'
  | 'snapshotting'
  | 'running'
  | 'local_review'
  | 'verifying'
  | 'ready_for_codex_review'
  | 'approved'
  | 'applied'
  | 'blocked'
  | 'failed'
  | 'timed_out'
  | 'cancelled'
  | 'stale'
  | 'rejected'

export type DevAgentFinding = {
  severity: 'critical' | 'major' | 'minor' | 'note'
  title: string
  detail: string
  path?: string | null
  line?: number | null
}

export type DevAgentCheck = {
  name: string
  argv: string[]
  cwd: string
  status: string
  duration_seconds?: number
  stdout?: string
  stderr?: string
}

export type DevAgentRun = {
  schema: 'career_local_dev_agent_result_v1'
  task_id: string
  status: DevAgentStatus
  phase: string
  role: DevAgentRole
  model: string
  model_digest?: string | null
  proposal_id?: string | null
  task: {
    objective?: string
    allowed_paths?: string[]
    acceptance_checks?: Array<{ name: string; argv: string[]; cwd: string }>
    risk?: string
    context_notes?: string
  }
  created_at: string
  started_at?: string | null
  finished_at?: string | null
  patch_sha256?: string | null
  reviewed_patch_sha256?: string | null
  reviewed_by?: string | null
  reviewed_at?: string | null
  attempt: number
  cancel_requested: boolean
  result: {
    status?: string
    summary?: string
    details?: string[]
    risks?: string[]
    blocking_reason?: string | null
    changed_files?: string[]
    diff_lines?: number
    change_statuses?: Record<string, string>
  }
  local_review: {
    status?: string
    summary?: string
    findings?: DevAgentFinding[]
  }
  secondary_review: {
    status?: string
    summary?: string
    findings?: DevAgentFinding[]
    model?: string
    model_digest?: string
  }
  verification: DevAgentCheck[]
  post_apply_verification: DevAgentCheck[]
  first_pass_ok: boolean
  approval_policy?: string | null
  auto_apply_receipt?: Record<string, unknown>
  patch_preview?: string
  patch_preview_truncated?: boolean
  error: string
  safety: Record<string, unknown>
}

export type DevAgentProposal = {
  schema: 'career_local_dev_proposal_v1'
  proposal_id: string
  planner_run_id: string
  status: 'proposed' | 'approved' | 'queued' | 'running' | 'applied' | 'rejected' | 'cancelled' | 'blocked'
  category: 'documentation' | 'tests' | 'investigation' | 'bounded_fix' | 'small_change' | 'refactor'
  objective: string
  evidence: string[]
  allowed_paths: string[]
  check_preset: DevAgentCheckPreset
  risk: 'low' | 'medium'
  priority: 'high' | 'medium' | 'low'
  estimated_files: number
  estimated_diff_lines: number
  created_at: string
  updated_at: string
  approved_at?: string | null
  rejected_at?: string | null
  task_id?: string | null
}

export type DevAgentModelState = {
  model: string
  digest: string
  qualified: boolean
  qualified_at?: string | null
  safe_applied_runs: number
  safe_apply_streak: number
  total_applied_runs: number
  first_pass_applied_runs: number
  first_pass_rate: number
  scope_violations: number
  privacy_violations: number
}

export type DevAgentOverview = {
  schema: 'career_local_dev_agent_overview_v1'
  generated_at: string
  counts: Partial<Record<DevAgentStatus, number>>
  active_runs: DevAgentRun[]
  recent_runs: DevAgentRun[]
  proposals: DevAgentProposal[]
  proposal_counts: Record<string, number>
  planner_runs: Array<{
    planner_run_id: string
    status: string
    trigger_source: string
    scheduled_for?: string | null
    model: string
    model_digest: string
    started_at: string
    finished_at?: string | null
    error: string
  }>
  rollout: {
    safe_applied_runs: number
    required_safe_runs: number
    remaining_safe_runs: number
    local_first_enabled: boolean
    qualified_at?: string | null
    selected_implementer_model?: string | null
    selected_implementer_digest?: string | null
    safe_apply_streak: number
    total_applied_runs: number
    first_pass_rate: number
    models: DevAgentModelState[]
    qualification?: { qualified?: boolean; results?: Record<string, unknown> }
  }
  autonomy: {
    tier: number
    auto_apply_enabled: boolean
    manually_paused: boolean
    paused_reason: string
    safe_applied_runs: number
    safe_apply_streak: number
    rolling_window: number
    rolling_first_pass_rate: number
    tier_one_required: number
    tier_two_required: number
    minimum_first_pass_rate: number
    evaluated_at: string
  }
  service: {
    online: boolean
    status: string
    heartbeat_at?: string | null
    next_planner_at?: string | null
    last_planner_at?: string | null
    last_defer_reason: string
    schedule_time: string
    timezone: string
    daily_implementation_cap: number
  }
  resources: {
    planner: { ok: boolean; reason: string; facts: Record<string, unknown> }
    implementer: { ok: boolean; reason: string; facts: Record<string, unknown> }
  }
  roles: Record<DevAgentRole, { model: string; sandbox: string; timeout_seconds: number }>
  limits: {
    max_changed_files: number
    max_diff_lines: number
    retry_count: number
    retention_days: number
    required_safe_runs: number
  }
  safety: {
    local_only: true
    online_fallback: false
    active_workspace_writes: false
    automatic_commit_or_push: false
    auto_apply_scope: string
    message: string
  }
}

export type DashboardTaskInput = {
  objective: unknown
  role: unknown
  allowedPaths: unknown
  verification: unknown
  risk?: unknown
  contextNotes?: unknown
}

type VerificationCheck = {
  name: string
  argv: string[]
  cwd: string
  timeout_seconds: number
}

const verificationChecks: Record<DevAgentCheckPreset, VerificationCheck[]> = {
  none: [],
  python: [
    {
      name: 'Python test suite',
      argv: ['python', '-m', 'pytest', '-q'],
      cwd: '.',
      timeout_seconds: 1800,
    },
  ],
  dashboard: [
    { name: 'Dashboard tests', argv: ['npm', 'test'], cwd: 'dashboard', timeout_seconds: 900 },
    { name: 'Dashboard typecheck', argv: ['npm', 'run', 'typecheck'], cwd: 'dashboard', timeout_seconds: 900 },
  ],
  raycast: [
    { name: 'Raycast tests', argv: ['npm', 'test'], cwd: 'raycast-job-search-hub', timeout_seconds: 900 },
    {
      name: 'Raycast typecheck',
      argv: ['npm', 'run', 'typecheck'],
      cwd: 'raycast-job-search-hub',
      timeout_seconds: 900,
    },
  ],
}

function runHelper<T>(args: string[], timeoutMs = quickHelperTimeoutMs): Promise<T> {
  return runPythonHelper<T>('developmentAgents', args, {
    timeoutMs,
    maxOutputBytes: 16 * 1024 * 1024,
    errorLabel: 'Development-agent helper',
  })
}

function isProtectedWritePath(path: string): boolean {
  const lower = path.toLowerCase()
  return protectedWritePaths.some((prefix) => lower === prefix.toLowerCase() || lower.startsWith(`${prefix.toLowerCase()}/`))
}

function normaliseAllowedPaths(value: unknown, role: DashboardDevAgentRole): string[] {
  if (!Array.isArray(value) || value.length < 1 || value.length > 10) {
    throw new Error('Choose between one and ten repository paths.')
  }
  const paths = [...new Set(value.map((item) => (typeof item === 'string' ? item.trim().replace(/^\.\//, '').replace(/\/$/, '') || '.' : '')))]
  if (paths.some((path) => !relativePathPattern.test(path) || path.includes('..'))) {
    throw new Error('Paths must be safe and relative to the repository.')
  }
  if (role === 'implementer' && paths.includes('.')) {
    throw new Error('Writing tasks need specific paths, not the whole repository.')
  }
  if (role === 'implementer' && paths.some(isProtectedWritePath)) {
    throw new Error('One of those paths is reserved for Main Codex.')
  }
  return paths
}

export function isDevAgentTaskId(value: unknown): value is string {
  return typeof value === 'string' && taskIdPattern.test(value)
}

export function isDevAgentProposalId(value: unknown): value is string {
  return typeof value === 'string' && proposalIdPattern.test(value)
}

export function isDevAgentAction(value: unknown): value is 'cancel' | 'reject' | 'apply' {
  return value === 'cancel' || value === 'reject' || value === 'apply'
}

export function isDevAgentControlAction(value: unknown): value is 'run_planner' | 'qualify_qwen36' | 'pause_autonomy' | 'resume_autonomy' {
  return value === 'run_planner' || value === 'qualify_qwen36' || value === 'pause_autonomy' || value === 'resume_autonomy'
}

export function buildDashboardTask(input: DashboardTaskInput): Record<string, unknown> {
  const objective = typeof input.objective === 'string' ? input.objective.trim() : ''
  if (objective.length < 10 || objective.length > 2_000) {
    throw new Error('Describe a bounded task in 10 to 2,000 characters.')
  }
  if (input.role !== 'explorer' && input.role !== 'implementer') {
    throw new Error('Choose explorer or implementer.')
  }
  if (!(typeof input.verification === 'string' && input.verification in verificationChecks)) {
    throw new Error('Choose a supported verification preset.')
  }
  const risk = input.risk === undefined ? 'low' : input.risk
  if (risk !== 'low' && risk !== 'medium') throw new Error('Dashboard tasks may be low or medium risk only.')
  const contextNotes = typeof input.contextNotes === 'string' ? input.contextNotes.trim() : ''
  if (contextNotes.length > 2_000) throw new Error('Context notes are limited to 2,000 characters.')
  const allowedPaths = normaliseAllowedPaths(input.allowedPaths, input.role)

  return {
    schema_version: 'career_local_dev_task_v1',
    objective,
    role: input.role,
    allowed_paths: allowedPaths,
    acceptance_checks: verificationChecks[input.verification as DevAgentCheckPreset],
    risk,
    context_notes: contextNotes,
    max_changed_files: input.role === 'implementer' ? 8 : 15,
    max_diff_lines: input.role === 'implementer' ? 600 : 1_000,
    timeout_seconds: input.role === 'implementer' ? 1_500 : 600,
  }
}

export async function getDevAgentOverview(): Promise<DevAgentOverview> {
  return runHelper<DevAgentOverview>(['status', '--limit', '30'])
}

export async function getDevAgentRun(taskId: string): Promise<DevAgentRun> {
  if (!isDevAgentTaskId(taskId)) throw new Error('Invalid development-agent task id.')
  return runHelper<DevAgentRun>(['show', '--task-id', taskId])
}

export async function startDevAgentRun(input: DashboardTaskInput): Promise<DevAgentRun> {
  const task = buildDashboardTask(input)
  const data = await runHelper<{ run: DevAgentRun; worker_pid?: number }>([
    'enqueue',
    '--task-json',
    JSON.stringify(task),
    '--spawn-worker',
  ])
  return data.run
}

export async function cancelDevAgentRun(taskId: string): Promise<DevAgentRun> {
  if (!isDevAgentTaskId(taskId)) throw new Error('Invalid development-agent task id.')
  return runHelper<DevAgentRun>(['cancel', '--task-id', taskId])
}

export async function rejectDevAgentRun(taskId: string): Promise<DevAgentRun> {
  if (!isDevAgentTaskId(taskId)) throw new Error('Invalid development-agent task id.')
  return runHelper<DevAgentRun>(['reject', '--task-id', taskId])
}

export async function applyDevAgentRun(taskId: string): Promise<DevAgentRun> {
  if (!isDevAgentTaskId(taskId)) throw new Error('Invalid development-agent task id.')
  return runHelper<DevAgentRun>(['apply', '--task-id', taskId], applyHelperTimeoutMs)
}

export async function runDevAgentPlanner(): Promise<{ started: true; pid: number }> {
  return runHelper<{ started: true; pid: number }>(['plan', '--trigger-source', 'manual', '--background'])
}

export async function benchmarkQwen36(): Promise<{ started: true; pid: number; candidate: string }> {
  return runHelper<{ started: true; pid: number; candidate: string }>([
    'model-benchmark',
    '--candidate',
    'qwen3.6:35b-a3b-coding-nvfp4',
    '--background',
  ])
}

export async function approveDevAgentProposal(input: {
  proposalId?: unknown
  objective?: unknown
  allowedPaths?: unknown
  verification?: unknown
}): Promise<{ proposal: DevAgentProposal; run: DevAgentRun; worker_pid?: number }> {
  if (!isDevAgentProposalId(input.proposalId)) throw new Error('Invalid development-agent proposal id.')
  const args = ['proposal-approve', '--proposal-id', input.proposalId]
  if (input.objective !== undefined) {
    const objective = typeof input.objective === 'string' ? input.objective.trim() : ''
    if (objective.length < 10 || objective.length > 2_000) throw new Error('Proposal objective must use 10 to 2,000 characters.')
    args.push('--objective', objective)
  }
  if (input.allowedPaths !== undefined) {
    const paths = normaliseAllowedPaths(input.allowedPaths, 'implementer')
    for (const path of paths) args.push('--allowed-path', path)
  }
  if (input.verification !== undefined) {
    if (!(typeof input.verification === 'string' && input.verification in verificationChecks)) {
      throw new Error('Choose a supported verification preset.')
    }
    args.push('--check-preset', input.verification)
  }
  args.push('--spawn-worker')
  return runHelper<{ proposal: DevAgentProposal; run: DevAgentRun; worker_pid?: number }>(args)
}

export async function rejectDevAgentProposal(proposalId: unknown): Promise<DevAgentProposal> {
  if (!isDevAgentProposalId(proposalId)) throw new Error('Invalid development-agent proposal id.')
  return runHelper<DevAgentProposal>(['proposal-reject', '--proposal-id', proposalId])
}

export async function setDevAgentAutonomyPaused(paused: boolean): Promise<DevAgentOverview['autonomy']> {
  return runHelper<DevAgentOverview['autonomy']>([
    paused ? 'autonomy-pause' : 'autonomy-resume',
    ...(paused ? ['--reason', 'Paused manually from the protected dashboard.'] : []),
  ])
}
