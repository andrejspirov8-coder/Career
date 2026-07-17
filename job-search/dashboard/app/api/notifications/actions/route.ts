import { dashboardJsonResponse, dashboardMutationAuthErrorResponse } from '../../../../lib/server/auth'
import {
  isNotificationId,
  isNotificationIndividualAction,
  performNotificationAction,
} from '../../../../lib/notification-data'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

type NotificationActionBody = {
  action?: unknown
  notificationId?: unknown
  notificationIds?: unknown
  enabled?: unknown
  markExisting?: unknown
}

export async function POST(request: Request) {
  const authError = dashboardMutationAuthErrorResponse(request)
  if (authError) return authError

  let body: NotificationActionBody
  try {
    body = (await request.json()) as NotificationActionBody
  } catch {
    return dashboardJsonResponse({ ok: false, error: 'Invalid notification request.' }, { status: 400 })
  }

  try {
    if (isNotificationIndividualAction(body.action)) {
      if (!isNotificationId(body.notificationId)) {
        return dashboardJsonResponse({ ok: false, error: 'Choose a valid notification.' }, { status: 400 })
      }
      return dashboardJsonResponse({
        ok: true,
        data: await performNotificationAction({
          action: body.action,
          notification_id: body.notificationId,
        }),
      })
    }

    if (body.action === 'read_all') {
      return dashboardJsonResponse({
        ok: true,
        data: await performNotificationAction({ action: 'read_all' }),
      })
    }

    if (body.action === 'set_desktop') {
      if (typeof body.enabled !== 'boolean' || typeof body.markExisting !== 'boolean') {
        return dashboardJsonResponse({ ok: false, error: 'Invalid desktop notification setting.' }, { status: 400 })
      }
      return dashboardJsonResponse({
        ok: true,
        data: await performNotificationAction({
          action: 'set_desktop',
          enabled: body.enabled,
          mark_existing: body.markExisting,
        }),
      })
    }

    if (body.action === 'desktop_delivered') {
      if (
        !Array.isArray(body.notificationIds)
        || body.notificationIds.length < 1
        || body.notificationIds.length > 50
        || !body.notificationIds.every(isNotificationId)
        || new Set(body.notificationIds).size !== body.notificationIds.length
      ) {
        return dashboardJsonResponse({ ok: false, error: 'Invalid desktop delivery list.' }, { status: 400 })
      }
      return dashboardJsonResponse({
        ok: true,
        data: await performNotificationAction({
          action: 'desktop_delivered',
          notification_ids: body.notificationIds,
        }),
      })
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Notification action failed.'
    return dashboardJsonResponse({ ok: false, error: message }, { status: 409 })
  }

  return dashboardJsonResponse({ ok: false, error: 'Unsupported notification action.' }, { status: 400 })
}
