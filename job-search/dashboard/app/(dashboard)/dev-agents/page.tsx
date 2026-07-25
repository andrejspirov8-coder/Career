import { requireDashboardPageAuth } from '@/lib/dashboard-page-auth'
import { getDevAgentOverview, type DevAgentOverview } from '@/lib/dev-agent-data'
import DevAgentConsole from './dev-agent-console'

export const dynamic = 'force-dynamic'

function unavailableOverview(): DevAgentOverview {
  return {
    schema: 'career_local_dev_agent_overview_v1',
    generated_at: new Date().toISOString(),
    counts: {},
    active_runs: [],
    recent_runs: [],
    proposals: [],
    proposal_counts: {},
    planner_runs: [],
    rollout: {
      safe_applied_runs: 0,
      required_safe_runs: 10,
      remaining_safe_runs: 10,
      local_first_enabled: false,
      qualified_at: null,
      selected_implementer_model: null,
      selected_implementer_digest: null,
      safe_apply_streak: 0,
      total_applied_runs: 0,
      first_pass_rate: 0,
      models: [],
    },
    autonomy: {
      tier: 0,
      auto_apply_enabled: false,
      manually_paused: false,
      paused_reason: '',
      safe_applied_runs: 0,
      safe_apply_streak: 0,
      rolling_window: 20,
      rolling_first_pass_rate: 0,
      tier_one_required: 10,
      tier_two_required: 20,
      minimum_first_pass_rate: 0.8,
      evaluated_at: new Date().toISOString(),
    },
    service: {
      online: false,
      status: 'unavailable',
      heartbeat_at: null,
      next_planner_at: null,
      last_planner_at: null,
      last_defer_reason: 'The coordinator is unavailable.',
      schedule_time: '19:00',
      timezone: 'Europe/Vilnius',
      daily_implementation_cap: 2,
    },
    resources: {
      planner: { ok: false, reason: 'Coordinator unavailable', facts: {} },
      implementer: { ok: false, reason: 'Coordinator unavailable', facts: {} },
    },
    roles: {
      planner: { model: 'gpt-oss:20b', sandbox: 'read-only', timeout_seconds: 600 },
      explorer: { model: 'gpt-oss:20b', sandbox: 'read-only', timeout_seconds: 600 },
      implementer: {
        model: 'qwen3.5:35b-a3b-coding-nvfp4',
        sandbox: 'workspace-write',
        timeout_seconds: 1500,
      },
      reviewer: { model: 'gpt-oss:20b', sandbox: 'read-only', timeout_seconds: 600 },
    },
    limits: {
      max_changed_files: 15,
      max_diff_lines: 1000,
      retry_count: 1,
      retention_days: 30,
      required_safe_runs: 10,
    },
    safety: {
      local_only: true,
      online_fallback: false,
      active_workspace_writes: false,
      automatic_commit_or_push: false,
      auto_apply_scope: 'Tier 2 documentation and tests only',
      message: 'The local coordinator is unavailable. Run the doctor check and refresh this page.',
    },
  }
}

export default async function DevAgentsPage() {
  await requireDashboardPageAuth('/dev-agents')
  let overview: DevAgentOverview
  try {
    overview = await getDevAgentOverview()
  } catch {
    overview = unavailableOverview()
  }

  return (
    <main className="workspaceMain">
      <DevAgentConsole initialOverview={overview} />
    </main>
  )
}
