'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useCallback, useEffect, useRef, useState } from 'react'

import LogoutButton from './logout-button'
import type { GlobalSearchResponse } from '../lib/global-search-types'
import type { NotificationOverview } from '../lib/notification-types'

const navigationGroups = [
  {
    label: 'Daily work',
    items: [
      { href: '/', label: 'Today' },
      { href: '/notifications', label: 'Notifications' },
      { href: '/opportunities', label: 'Opportunities' },
      { href: '/applications', label: 'Applications' },
      { href: '/recruiters', label: 'Recruiters' },
    ],
  },
  {
    label: 'Manage',
    items: [
      { href: '/automation', label: 'Automation' },
      { href: '/dev-agents', label: 'Development Agents' },
      { href: '/cvs', label: 'CV Studio' },
      { href: '/insights', label: 'Insights' },
      { href: '/settings', label: 'Settings' },
    ],
  },
]

export default function AppNavigation() {
  const pathname = usePathname()
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState<GlobalSearchResponse | null>(null)
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchBusy, setSearchBusy] = useState(false)
  const [hydrated, setHydrated] = useState(false)
  const [notificationOverview, setNotificationOverview] = useState<NotificationOverview | null>(null)
  const deliveringDesktop = useRef(false)

  useEffect(() => setHydrated(true), [])

  const deliverDesktopNotifications = useCallback(async (overview: NotificationOverview) => {
    if (
      deliveringDesktop.current
      || !overview.settings.desktop_enabled
      || !overview.desktop_pending.length
      || !('Notification' in window)
      || Notification.permission !== 'granted'
    ) return

    deliveringDesktop.current = true
    const pending = overview.desktop_pending
    try {
      let alert: Notification
      if (pending.length === 1) {
        const item = pending[0]
        alert = new Notification(item.title, {
          body: item.body,
          tag: item.notification_id,
        })
        alert.onclick = () => {
          window.focus()
          window.location.assign(item.href)
        }
      } else {
        alert = new Notification(`${pending.length} Career updates need attention`, {
          body: pending.slice(0, 3).map((item) => item.title).join(' · '),
          tag: 'career-notification-inbox',
        })
        alert.onclick = () => {
          window.focus()
          window.location.assign('/notifications')
        }
      }
      const response = await fetch('/api/notifications/actions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'desktop_delivered',
          notificationIds: pending.map((item) => item.notification_id),
        }),
      })
      const payload = (await response.json()) as { ok?: boolean; data?: NotificationOverview }
      if (response.ok && payload.ok && payload.data) setNotificationOverview(payload.data)
    } catch {
      // Keep pending delivery state so a later refresh can retry.
    } finally {
      deliveringDesktop.current = false
    }
  }, [])

  const refreshNotifications = useCallback(async () => {
    try {
      const response = await fetch('/api/notifications/overview', { cache: 'no-store' })
      const payload = (await response.json()) as { ok?: boolean; data?: NotificationOverview }
      if (!response.ok || !payload.ok || !payload.data) return
      setNotificationOverview(payload.data)
      await deliverDesktopNotifications(payload.data)
    } catch {
      // Navigation remains usable during a short local helper failure.
    }
  }, [deliverDesktopNotifications])

  useEffect(() => {
    void refreshNotifications()
    const interval = window.setInterval(() => void refreshNotifications(), 30_000)
    const refreshNow = () => void refreshNotifications()
    window.addEventListener('career-notifications-changed', refreshNow)
    return () => {
      window.clearInterval(interval)
      window.removeEventListener('career-notifications-changed', refreshNow)
    }
  }, [pathname, refreshNotifications])

  useEffect(() => {
    const cleanQuery = query.trim()
    if (cleanQuery.length < 2) {
      setSearch(null)
      setSearchBusy(false)
      return
    }
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      setSearchBusy(true)
      void fetch(`/api/search?q=${encodeURIComponent(cleanQuery)}`, {
        cache: 'no-store',
        signal: controller.signal,
      })
        .then(async (response) => {
          const payload = (await response.json()) as { ok?: boolean; data?: GlobalSearchResponse }
          if (!response.ok || !payload.ok || !payload.data) throw new Error('Search failed.')
          setSearch(payload.data)
        })
        .catch((error) => {
          if (error instanceof DOMException && error.name === 'AbortError') return
          setSearch({ query: cleanQuery, results: [] })
        })
        .finally(() => {
          if (!controller.signal.aborted) setSearchBusy(false)
        })
    }, 250)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [query])

  return (
    <nav className="appNavigation" aria-label="Career workspace">
      <Link className="appBrand" href="/">
        <span className="brandMark" aria-hidden="true">C</span>
        <span><strong>Career</strong><small>Local workspace</small></span>
      </Link>
      <div className="globalSearch" onKeyDown={(event) => {
        if (event.key === 'Escape') setSearchOpen(false)
      }}>
        <label htmlFor="global-search">Find anything</label>
        <input
          id="global-search"
          type="search"
          disabled={!hydrated}
          value={query}
          onChange={(event) => {
            setQuery(event.target.value.slice(0, 80))
            setSearchOpen(true)
          }}
          onFocus={() => setSearchOpen(true)}
          placeholder="Jobs, people, CVs"
          autoComplete="off"
        />
        {searchOpen && query.trim().length >= 2 ? (
          <div className="globalSearchResults">
            {searchBusy ? <span>Searching…</span> : search?.results.length ? search.results.map((result) => (
              <Link href={result.href} key={`${result.kind}-${result.id}`} onClick={() => setSearchOpen(false)}>
                <small>{result.kind}</small>
                <strong>{result.title}</strong>
                <span>{result.subtitle}</span>
              </Link>
            )) : <span>No matching jobs, people, or CVs.</span>}
          </div>
        ) : null}
      </div>
      <div className="navLinks">
        {navigationGroups.map((group) => (
          <div className="navGroup" key={group.label}>
            <span className="navGroupLabel">{group.label}</span>
            <div className="navGroupLinks">
              {group.items.map((item) => {
                const active = item.href === '/' ? pathname === '/' : pathname.startsWith(item.href)
                const unread = item.href === '/notifications' ? notificationOverview?.counts.unread || 0 : 0
                return (
                  <Link aria-current={active ? 'page' : undefined} className={active ? 'active' : ''} href={item.href} key={item.href}>
                    <span>{item.label}</span>
                    {unread ? <em aria-label={`${unread} unread`}>{unread > 99 ? '99+' : unread}</em> : null}
                  </Link>
                )
              })}
            </div>
          </div>
        ))}
      </div>
      <LogoutButton />
    </nav>
  )
}
