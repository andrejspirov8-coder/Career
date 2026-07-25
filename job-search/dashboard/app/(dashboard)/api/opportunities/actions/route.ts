import { dashboardJsonResponse, dashboardMutationAuthErrorResponse } from '@/lib/server/auth'
import {
  isOpportunityId,
  runOpportunityAction,
  type OpportunityActionName,
} from '@/lib/opportunity-data'
import { safeExternalHttpUrl } from '@/lib/safe-url'

export const dynamic = 'force-dynamic'

const safeActions = new Set<OpportunityActionName>([
  'mark_review',
  'mark_skipped',
  'mark_apply_ready',
  'generate_pack',
  'mark_applied',
  'log_application',
  'update_application_outcome',
  'snooze_followup',
  'undo_last_decision',
])

const skipReasons = new Set([
  'not_relevant',
  'location',
  'salary',
  'seniority',
  'company',
  'duplicate',
  'closed',
  'other',
])

export async function POST(request: Request) {
  const authError = dashboardMutationAuthErrorResponse(request)
  if (authError) return authError

  try {
    const body = (await request.json()) as {
      action?: unknown
      opportunityId?: unknown
      applicationUrl?: unknown
      applicationNotes?: unknown
      applicationOutcome?: unknown
      decisionReason?: unknown
      decisionNote?: unknown
      requestId?: unknown
    }
    if (!body.action) {
      return dashboardJsonResponse({ ok: false, error: 'Missing action.' }, { status: 400 })
    }
    if (!safeActions.has(body.action as OpportunityActionName)) {
      return dashboardJsonResponse({ ok: false, error: 'Unsupported opportunity action.' }, { status: 400 })
    }
    if (!isOpportunityId(body.opportunityId)) {
      return dashboardJsonResponse({ ok: false, error: 'A valid opportunityId is required.' }, { status: 400 })
    }

    let applicationUrl: string | undefined
    if (body.applicationUrl !== undefined) {
      const validatedUrl = safeExternalHttpUrl(body.applicationUrl)
      if (!validatedUrl) {
        return dashboardJsonResponse(
          { ok: false, error: 'A valid HTTP applicationUrl is required.' },
          { status: 400 },
        )
      }
      applicationUrl = validatedUrl
    }

    let applicationNotes: string | undefined
    if (body.applicationNotes !== undefined) {
      if (typeof body.applicationNotes !== 'string' || body.applicationNotes.length > 1000) {
        return dashboardJsonResponse(
          { ok: false, error: 'Application notes must be 1,000 characters or fewer.' },
          { status: 400 },
        )
      }
      applicationNotes = body.applicationNotes.trim()
    }

    let applicationOutcome: string | undefined
    if (body.applicationOutcome !== undefined) {
      const allowedOutcomes = new Set(['screening', 'interview', 'offer', 'rejected', 'withdrawn'])
      if (typeof body.applicationOutcome !== 'string' || !allowedOutcomes.has(body.applicationOutcome)) {
        return dashboardJsonResponse(
          { ok: false, error: 'Choose a valid application outcome.' },
          { status: 400 },
        )
      }
      applicationOutcome = body.applicationOutcome
    }
    if (body.action === 'update_application_outcome' && !applicationOutcome) {
      return dashboardJsonResponse(
        { ok: false, error: 'Choose an application outcome.' },
        { status: 400 },
      )
    }

    let decisionReason: string | undefined
    if (body.action === 'mark_skipped') {
      if (typeof body.decisionReason !== 'string' || !skipReasons.has(body.decisionReason)) {
        return dashboardJsonResponse(
          { ok: false, error: 'Choose why this role is not suitable.' },
          { status: 400 },
        )
      }
      decisionReason = body.decisionReason
    }

    let requestId: string | undefined
    if (body.requestId !== undefined) {
      if (typeof body.requestId !== 'string' || body.requestId.length > 200) {
        return dashboardJsonResponse({ ok: false, error: 'requestId must be 200 characters or fewer.' }, { status: 400 })
      }
      requestId = body.requestId.trim()
    }

    let decisionNote: string | undefined
    if (body.decisionNote !== undefined) {
      if (typeof body.decisionNote !== 'string' || body.decisionNote.length > 500) {
        return dashboardJsonResponse(
          { ok: false, error: 'Decision notes must be 500 characters or fewer.' },
          { status: 400 },
        )
      }
      decisionNote = body.decisionNote.trim()
    }

    return dashboardJsonResponse({
      ok: true,
      data: await runOpportunityAction(body.action as OpportunityActionName, body.opportunityId, {
        applicationUrl,
        applicationNotes,
        applicationOutcome,
        decisionReason,
        decisionNote,
        requestId,
      }),
    })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Action failed.'
    const status = error instanceof SyntaxError ? 400 : 500
    return dashboardJsonResponse({ ok: false, error: message }, { status })
  }
}
