import {
  applyDevAgentRun,
  approveDevAgentProposal,
  benchmarkQwen36,
  cancelDevAgentRun,
  isDevAgentAction,
  isDevAgentControlAction,
  isDevAgentProposalId,
  isDevAgentTaskId,
  rejectDevAgentProposal,
  rejectDevAgentRun,
  runDevAgentPlanner,
  setDevAgentAutonomyPaused,
  startDevAgentRun,
  type DashboardTaskInput,
} from '@/lib/dev-agent-data'
import { dashboardJsonResponse, dashboardMutationAuthErrorResponse } from '@/lib/server/auth'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

type DevAgentActionBody = DashboardTaskInput & {
  action?: unknown
  taskId?: unknown
  proposalId?: unknown
  verification?: unknown
}

export async function POST(request: Request) {
  const authError = dashboardMutationAuthErrorResponse(request)
  if (authError) return authError

  let body: DevAgentActionBody
  try {
    body = (await request.json()) as DevAgentActionBody
  } catch {
    return dashboardJsonResponse({ ok: false, error: 'Invalid development-agent request.' }, { status: 400 })
  }

  try {
    if (body.action === 'start') {
      const run = await startDevAgentRun(body)
      return dashboardJsonResponse({ ok: true, data: { run } }, { status: 202 })
    }

    if (isDevAgentControlAction(body.action)) {
      if (body.action === 'run_planner') {
        return dashboardJsonResponse({ ok: true, data: await runDevAgentPlanner() }, { status: 202 })
      }
      if (body.action === 'qualify_qwen36') {
        return dashboardJsonResponse({ ok: true, data: await benchmarkQwen36() }, { status: 202 })
      }
      return dashboardJsonResponse({
        ok: true,
        data: { autonomy: await setDevAgentAutonomyPaused(body.action === 'pause_autonomy') },
      })
    }

    if (body.action === 'approve_proposal') {
      const data = await approveDevAgentProposal(body)
      return dashboardJsonResponse({ ok: true, data }, { status: 202 })
    }

    if (body.action === 'reject_proposal') {
      if (!isDevAgentProposalId(body.proposalId)) {
        return dashboardJsonResponse({ ok: false, error: 'Invalid development-agent proposal id.' }, { status: 400 })
      }
      return dashboardJsonResponse({ ok: true, data: { proposal: await rejectDevAgentProposal(body.proposalId) } })
    }

    if (isDevAgentAction(body.action)) {
      if (!isDevAgentTaskId(body.taskId)) {
        return dashboardJsonResponse({ ok: false, error: 'Invalid development-agent task id.' }, { status: 400 })
      }
      const run = body.action === 'cancel'
        ? await cancelDevAgentRun(body.taskId)
        : body.action === 'reject'
          ? await rejectDevAgentRun(body.taskId)
          : await applyDevAgentRun(body.taskId)
      return dashboardJsonResponse({ ok: true, data: { run } })
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Development-agent action failed.'
    return dashboardJsonResponse({ ok: false, error: message }, { status: 409 })
  }

  return dashboardJsonResponse({ ok: false, error: 'Unsupported development-agent request.' }, { status: 400 })
}
