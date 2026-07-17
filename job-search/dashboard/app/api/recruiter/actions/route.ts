import {
  approveRecruiterNote,
  bulkMarkRecruitersReview,
  bulkMarkRecruitersSkipped,
  markRecruiterReview,
  markRecruiterSkipped,
  recordRecruiterOperatorAction,
  runRecruiterAction,
  updateRecruiterNote,
  type RecruiterActionName,
  type RecruiterRunActionName,
} from '../../../../lib/recruiter-data'
import { dashboardJsonResponse, dashboardMutationAuthErrorResponse } from '../../../../lib/server/auth'
import { safeLinkedInProfileUrl } from '../../../../lib/recruiter-links'

export const dynamic = 'force-dynamic'

const runActions = new Set<RecruiterRunActionName>(['preflight', 'rank_existing'])
const operatorActions = new Set<RecruiterActionName>([
  'copy_note_recorded',
  'mark_sent_manual',
  'mark_pending',
  'mark_replied',
  'mark_accepted',
  'mark_rejected',
  'snooze_followup',
])

export async function POST(request: Request) {
  const authError = dashboardMutationAuthErrorResponse(request)
  if (authError) return authError

  try {
    const body = (await request.json()) as { action?: string; profileUrl?: string; profileUrls?: string[]; note?: string }
    const action = body.action
    if (!action) {
      return dashboardJsonResponse({ ok: false, error: 'Missing action.' }, { status: 400 })
    }

    if (action === 'bulk_approve' || action === 'bulk_approve_note') {
      return dashboardJsonResponse(
        { ok: false, error: 'Bulk approval is not supported from the dashboard.' },
        { status: 400 },
      )
    }

    if (runActions.has(action as RecruiterRunActionName)) {
      const result = await runRecruiterAction(action as RecruiterRunActionName)
      return dashboardJsonResponse({ ok: true, data: result })
    }

    if (action === 'approve_note') {
      const profileUrl = safeLinkedInProfileUrl(body.profileUrl)
      if (!profileUrl || !validNote(body.note)) {
        return dashboardJsonResponse(
          { ok: false, error: 'A valid LinkedIn profileUrl and note of 1 to 280 characters are required.' },
          { status: 400 },
        )
      }
      return dashboardJsonResponse({ ok: true, data: await approveRecruiterNote(profileUrl, body.note) })
    }

    if (action === 'update_note') {
      const profileUrl = safeLinkedInProfileUrl(body.profileUrl)
      if (!profileUrl || !validNote(body.note)) {
        return dashboardJsonResponse(
          { ok: false, error: 'A valid LinkedIn profileUrl and note of 1 to 280 characters are required.' },
          { status: 400 },
        )
      }
      return dashboardJsonResponse({ ok: true, data: await updateRecruiterNote(profileUrl, body.note) })
    }

    if (action === 'mark_skipped') {
      const profileUrl = safeLinkedInProfileUrl(body.profileUrl)
      if (!profileUrl) {
        return dashboardJsonResponse({ ok: false, error: 'A valid LinkedIn profileUrl is required.' }, { status: 400 })
      }
      return dashboardJsonResponse({ ok: true, data: await markRecruiterSkipped(profileUrl) })
    }

    if (action === 'mark_review') {
      const profileUrl = safeLinkedInProfileUrl(body.profileUrl)
      if (!profileUrl) {
        return dashboardJsonResponse({ ok: false, error: 'A valid LinkedIn profileUrl is required.' }, { status: 400 })
      }
      return dashboardJsonResponse({ ok: true, data: await markRecruiterReview(profileUrl) })
    }

    if (action === 'bulk_mark_skipped') {
      const profileUrls = validProfileUrls(body.profileUrls)
      if (!profileUrls) {
        return dashboardJsonResponse(
          { ok: false, error: 'Between 1 and 100 valid LinkedIn profileUrls are required.' },
          { status: 400 },
        )
      }
      return dashboardJsonResponse({ ok: true, data: await bulkMarkRecruitersSkipped(profileUrls) })
    }

    if (action === 'bulk_mark_review') {
      const profileUrls = validProfileUrls(body.profileUrls)
      if (!profileUrls) {
        return dashboardJsonResponse(
          { ok: false, error: 'Between 1 and 100 valid LinkedIn profileUrls are required.' },
          { status: 400 },
        )
      }
      return dashboardJsonResponse({ ok: true, data: await bulkMarkRecruitersReview(profileUrls) })
    }

    if (operatorActions.has(action as RecruiterActionName)) {
      const profileUrl = safeLinkedInProfileUrl(body.profileUrl)
      if (!profileUrl) {
        return dashboardJsonResponse({ ok: false, error: 'A valid LinkedIn profileUrl is required.' }, { status: 400 })
      }
      if ((action === 'copy_note_recorded' || action === 'mark_sent_manual') && !validNote(body.note)) {
        return dashboardJsonResponse(
          { ok: false, error: 'A note of 1 to 280 characters is required.' },
          { status: 400 },
        )
      }
      return dashboardJsonResponse({
        ok: true,
        data: await recordRecruiterOperatorAction(action as RecruiterActionName, profileUrl, body.note || ''),
      })
    }

    return dashboardJsonResponse({ ok: false, error: 'Unsupported dashboard action.' }, { status: 400 })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Action failed.'
    return dashboardJsonResponse({ ok: false, error: message }, { status: 500 })
  }
}

function validNote(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0 && value.length <= 280
}

function validProfileUrls(values: unknown): string[] | null {
  if (!Array.isArray(values) || values.length < 1 || values.length > 100) return null
  const urls = values.map(safeLinkedInProfileUrl)
  if (urls.some((value) => !value)) return null
  return Array.from(new Set(urls as string[]))
}
