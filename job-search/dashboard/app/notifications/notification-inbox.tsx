'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'

import type {
  CareerNotification,
  NotificationCategory,
  NotificationIndividualAction,
  NotificationOverview,
} from '../../lib/notification-types'

type InboxView = 'inbox' | 'snoozed' | 'archived'
type ApiResponse = { ok?: boolean; data?: NotificationOverview; error?: string }

const categories: Array<{ value: 'all' | NotificationCategory; label: string }> = [
  { value: 'all', label: 'All updates' },
  { value: 'application', label: 'Applications' },
  { value: 'opportunity', label: 'Opportunities' },
  { value: 'automation', label: 'Automation' },
  { value: 'system', label: 'System' },
]

function formatAbsoluteTime(value: string): string {
  return new Date(value).toLocaleString('en-GB', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Europe/Vilnius',
  })
}

function formatTime(value: string, referenceNow: number): string {
  const date = new Date(value)
  const differenceMinutes = Math.round((referenceNow - date.getTime()) / 60_000)
  if (differenceMinutes >= 0 && differenceMinutes < 1) return 'Just now'
  if (differenceMinutes >= 1 && differenceMinutes < 60) return `${differenceMinutes}m ago`
  if (differenceMinutes >= 60 && differenceMinutes < 24 * 60) return `${Math.floor(differenceMinutes / 60)}h ago`
  return formatAbsoluteTime(value)
}

function categoryLabel(value: NotificationCategory): string {
  if (value === 'opportunity') return 'Opportunity'
  if (value === 'application') return 'Application'
  if (value === 'automation') return 'Automation'
  return 'System'
}

function actionNotice(action: string): string {
  const labels: Record<string, string> = {
    read: 'Marked as read.',
    unread: 'Marked as unread.',
    dismiss: 'Moved to archive.',
    restore: 'Restored to the inbox.',
    snooze_day: 'Snoozed until tomorrow.',
    snooze_week: 'Snoozed for seven days.',
    clear_snooze: 'Returned to the inbox.',
    read_all: 'All current notifications marked as read.',
  }
  return labels[action] || 'Notification updated.'
}

export default function NotificationInbox({ initialOverview }: { initialOverview: NotificationOverview }) {
  const [overview, setOverview] = useState(initialOverview)
  const [view, setView] = useState<InboxView>('inbox')
  const [category, setCategory] = useState<'all' | NotificationCategory>('all')
  const [selectedId, setSelectedId] = useState(initialOverview.inbox[0]?.notification_id || '')
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [hydrated, setHydrated] = useState(false)
  const [displayNow, setDisplayNow] = useState(() => Date.parse(initialOverview.generated_at))
  const [permission, setPermission] = useState<NotificationPermission | 'unsupported'>('default')

  useEffect(() => {
    setHydrated(true)
    setDisplayNow(Date.now())
    setPermission('Notification' in window ? Notification.permission : 'unsupported')
    void refresh(false)
  }, [])

  const sourceRows = overview[view]
  const rows = useMemo(
    () => sourceRows.filter((item) => category === 'all' || item.category === category),
    [category, sourceRows],
  )
  const selected = rows.find((item) => item.notification_id === selectedId) || rows[0] || null

  useEffect(() => {
    if (selected && selected.notification_id !== selectedId) setSelectedId(selected.notification_id)
    if (!selected && selectedId) setSelectedId('')
  }, [selected, selectedId])

  function install(next: NotificationOverview) {
    setOverview(next)
    const generatedAt = Date.parse(next.generated_at)
    if (Number.isFinite(generatedAt)) setDisplayNow(generatedAt)
    window.dispatchEvent(new Event('career-notifications-changed'))
  }

  async function postAction(body: Record<string, unknown>): Promise<NotificationOverview> {
    const response = await fetch('/api/notifications/actions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const payload = (await response.json()) as ApiResponse
    if (!response.ok || !payload.ok || !payload.data) {
      throw new Error(payload.error || 'Notification could not be updated.')
    }
    install(payload.data)
    return payload.data
  }

  async function mutate(action: NotificationIndividualAction, notificationId: string, silent = false) {
    setBusy(`${action}:${notificationId}`)
    setError('')
    if (!silent) setNotice('')
    try {
      await postAction({ action, notificationId })
      if (!silent) setNotice(actionNotice(action))
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : 'Notification could not be updated.')
    } finally {
      setBusy('')
    }
  }

  async function selectItem(item: CareerNotification) {
    setSelectedId(item.notification_id)
    if (!item.is_unread || view === 'archived') return
    await mutate('read', item.notification_id, true)
  }

  async function markAllRead() {
    setBusy('read_all')
    setError('')
    setNotice('')
    try {
      await postAction({ action: 'read_all' })
      setNotice(actionNotice('read_all'))
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : 'Notifications could not be updated.')
    } finally {
      setBusy('')
    }
  }

  async function refresh(showNotice = true) {
    setBusy('refresh')
    setError('')
    try {
      const response = await fetch('/api/notifications/overview?force=1', { cache: 'no-store' })
      const payload = (await response.json()) as ApiResponse
      if (!response.ok || !payload.ok || !payload.data) throw new Error(payload.error || 'Inbox could not be refreshed.')
      install(payload.data)
      if (showNotice) setNotice('Inbox refreshed.')
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : 'Inbox could not be refreshed.')
    } finally {
      setBusy('')
    }
  }

  async function setDesktop(enabled: boolean) {
    setBusy('desktop')
    setError('')
    setNotice('')
    try {
      if (enabled) {
        if (!('Notification' in window)) {
          setPermission('unsupported')
          throw new Error('Desktop alerts are not supported in this browser.')
        }
        const nextPermission = Notification.permission === 'granted'
          ? 'granted'
          : await Notification.requestPermission()
        setPermission(nextPermission)
        if (nextPermission !== 'granted') {
          throw new Error('Desktop alerts remain off. Allow notifications in the browser to enable them.')
        }
      }
      await postAction({ action: 'set_desktop', enabled, markExisting: enabled })
      if (enabled) {
        new Notification('Career alerts enabled', {
          body: 'New searches, strong roles, deadlines, and follow-ups can now appear on this Mac while the dashboard is open.',
          tag: 'career-notifications-enabled',
        })
      }
      setNotice(enabled ? 'Desktop alerts enabled for future updates.' : 'Desktop alerts disabled.')
    } catch (desktopError) {
      setError(desktopError instanceof Error ? desktopError.message : 'Desktop alert setting could not be changed.')
    } finally {
      setBusy('')
    }
  }

  const desktopStatus = permission === 'unsupported'
    ? 'Unavailable in this browser'
    : permission === 'denied'
      ? 'Blocked by browser permission'
      : overview.settings.desktop_enabled && permission === 'granted'
        ? 'Enabled while the dashboard is open'
        : permission === 'granted'
          ? 'Browser permission ready · alerts off'
          : 'Off until you enable it'

  return (
    <>
      <div className="workspaceHeading notificationHeading">
        <div>
          <div className="eyebrow">Private attention inbox</div>
          <h1>Notifications</h1>
          <p className="muted">Search results, strong roles, deadlines, and follow-ups in one local queue.</p>
        </div>
        <div className={`notificationUnreadCount ${overview.counts.unread ? 'hasUnread' : ''}`}>
          <strong>{overview.counts.unread}</strong>
          <span>unread</span>
        </div>
      </div>

      {error ? <div className="banner" role="alert">{error}</div> : null}
      {notice ? <div className="noticeBanner" role="status">{notice}</div> : null}

      <section className="notificationStatusStrip" aria-label="Notification status">
        <div><span>Urgent</span><strong>{overview.counts.urgent}</strong></div>
        <div><span>Needs attention</span><strong>{overview.counts.attention}</strong></div>
        <div><span>Snoozed</span><strong>{overview.counts.snoozed}</strong></div>
        <div><span>History</span><strong>{overview.counts.archived}</strong></div>
        <div className="notificationStatusActions">
          <button className="textButton" disabled={!hydrated || Boolean(busy) || !overview.counts.unread} onClick={markAllRead} type="button">Mark all read</button>
          <button className="textButton" disabled={!hydrated || Boolean(busy)} onClick={() => void refresh()} type="button">{busy === 'refresh' ? 'Refreshing…' : 'Refresh'}</button>
        </div>
      </section>

      <div className="notificationWorkspace">
        <section className="workspacePanel notificationQueue" aria-labelledby="notification-queue-title">
          <div className="notificationQueueTools">
            <div className="notificationTabs" role="group" aria-label="Notification views">
              <button aria-pressed={view === 'inbox'} className={view === 'inbox' ? 'active' : ''} onClick={() => setView('inbox')} type="button">Inbox <span>{overview.inbox.length}</span></button>
              <button aria-pressed={view === 'snoozed'} className={view === 'snoozed' ? 'active' : ''} onClick={() => setView('snoozed')} type="button">Snoozed <span>{overview.snoozed.length}</span></button>
              <button aria-pressed={view === 'archived'} className={view === 'archived' ? 'active' : ''} onClick={() => setView('archived')} type="button">History <span>{overview.archived.length}</span></button>
            </div>
            <label>
              <span>Show</span>
              <select aria-label="Notification category" value={category} onChange={(event) => setCategory(event.target.value as typeof category)}>
                {categories.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
          </div>
          <h2 className="srOnly" id="notification-queue-title">Notification queue</h2>
          {rows.length ? (
            <div className="notificationRows">
              {rows.map((item) => (
                <button
                  className={`${selected?.notification_id === item.notification_id ? 'selected' : ''} ${item.is_unread ? 'unread' : ''}`}
                  key={item.notification_id}
                  onClick={() => void selectItem(item)}
                  type="button"
                >
                  <span className={`notificationPriority priority-${item.priority}`} aria-hidden="true" />
                  <span className="notificationRowCopy">
                    <span><em>{categoryLabel(item.category)}</em><small>{formatTime(item.occurred_at, displayNow)}</small></span>
                    <strong>{item.title}</strong>
                    <span>{item.body}</span>
                  </span>
                  {item.is_unread ? <span className="notificationUnreadDot"><span className="srOnly">Unread</span></span> : null}
                </button>
              ))}
            </div>
          ) : (
            <div className="emptyState notificationEmpty">
              <strong>{view === 'inbox' ? 'Nothing needs attention here.' : view === 'snoozed' ? 'No notifications are snoozed.' : 'No notification history yet.'}</strong>
              <span>{category === 'all' ? 'The inbox will update automatically.' : 'Try showing all update types.'}</span>
            </div>
          )}
        </section>

        <section className="workspacePanel notificationDetail" aria-labelledby="notification-detail-title">
          {selected ? (
            <>
              <div className="notificationDetailHeading">
                <span className={`priorityLabel priority-${selected.priority}`}>{selected.priority}</span>
                <span>{categoryLabel(selected.category)} · {formatTime(selected.occurred_at, displayNow)}</span>
              </div>
              <h2 id="notification-detail-title">{selected.title}</h2>
              <p>{selected.body}</p>
              {selected.snoozed_until && selected.is_snoozed ? (
                <div className="notificationSnoozeNote">Snoozed until {formatAbsoluteTime(selected.snoozed_until)}</div>
              ) : null}
              {selected.resolved_at ? <div className="notificationResolvedNote">This condition is no longer active.</div> : null}
              <div className="notificationPrimaryActions">
                <Link className="buttonLink" href={selected.href}>Open related workspace</Link>
                {view === 'snoozed' ? (
                  <button className="button secondary" disabled={Boolean(busy)} onClick={() => void mutate('clear_snooze', selected.notification_id)} type="button">Return to inbox</button>
                ) : null}
                {view === 'archived' && selected.dismissed_at && !selected.resolved_at ? (
                  <button className="button secondary" disabled={Boolean(busy)} onClick={() => void mutate('restore', selected.notification_id)} type="button">Restore</button>
                ) : null}
              </div>
              {view === 'inbox' ? (
                <div className="notificationSecondaryActions">
                  <button disabled={Boolean(busy)} onClick={() => void mutate(selected.is_unread ? 'read' : 'unread', selected.notification_id)} type="button">Mark {selected.is_unread ? 'read' : 'unread'}</button>
                  <button disabled={Boolean(busy)} onClick={() => void mutate('snooze_day', selected.notification_id)} type="button">Snooze 1 day</button>
                  <button disabled={Boolean(busy)} onClick={() => void mutate('snooze_week', selected.notification_id)} type="button">Snooze 7 days</button>
                  <button disabled={Boolean(busy)} onClick={() => void mutate('dismiss', selected.notification_id)} type="button">Dismiss</button>
                </div>
              ) : null}
            </>
          ) : (
            <div className="emptyState notificationDetailEmpty">
              <strong>Select an update.</strong>
              <span>Its context and safe actions will appear here.</span>
            </div>
          )}
        </section>
      </div>

      <section className="desktopAlertSettings" aria-labelledby="desktop-alert-title">
        <div>
          <div className="eyebrow">Optional desktop delivery</div>
          <h2 id="desktop-alert-title">Show important updates on this Mac</h2>
          <p>Alerts use the browser’s local notification permission. Nothing is sent to an email, phone, or outside service.</p>
        </div>
        <div>
          <span>{desktopStatus}</span>
          <button
            className={overview.settings.desktop_enabled ? 'button secondary' : 'button'}
            disabled={!hydrated || busy === 'desktop' || permission === 'denied' || permission === 'unsupported'}
            onClick={() => void setDesktop(!overview.settings.desktop_enabled)}
            type="button"
          >
            {busy === 'desktop' ? 'Saving…' : overview.settings.desktop_enabled ? 'Turn off desktop alerts' : 'Enable desktop alerts'}
          </button>
        </div>
      </section>
    </>
  )
}
