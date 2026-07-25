import { requireDashboardPageAuth } from '@/lib/dashboard-page-auth'
import { getNotificationOverview } from '@/lib/notification-data'
import type { NotificationOverview } from '@/lib/notification-types'
import NotificationInbox from './notification-inbox'

export const dynamic = 'force-dynamic'

function unavailableOverview(): NotificationOverview {
  const now = new Date().toISOString()
  return {
    schema: 'career_notification_overview_v1',
    generated_at: now,
    counts: { active: 0, unread: 0, urgent: 0, attention: 0, snoozed: 0, archived: 0 },
    inbox: [],
    snoozed: [],
    archived: [],
    desktop_pending: [],
    settings: { desktop_enabled: false, updated_at: now },
  }
}

export default async function NotificationsPage() {
  await requireDashboardPageAuth('/notifications')
  const overview = await getNotificationOverview().catch(unavailableOverview)
  return (
    <main className="workspaceMain">
      <NotificationInbox initialOverview={overview} />
    </main>
  )
}
