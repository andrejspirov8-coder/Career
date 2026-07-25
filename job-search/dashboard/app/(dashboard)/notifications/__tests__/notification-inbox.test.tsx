import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React from 'react'

vi.mock('next/link', () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) =>
    <a href={href}>{children}</a>,
}))

import NotificationInbox from '../notification-inbox'
import type { NotificationOverview } from '@/lib/notification-types'

const fakeOverview: NotificationOverview = {
  schema: 'career_notification_overview_v1',
  generated_at: '2026-07-25T10:00:00Z',
  counts: { active: 2, unread: 2, urgent: 1, attention: 0, snoozed: 0, archived: 3 },
  inbox: [
    {
      notification_id: 'n1',
      category: 'opportunity',
      kind: 'strong_role',
      priority: 'urgent',
      title: 'Senior Engineer at Example',
      body: 'Strong match detected.',
      href: '/opportunities/opp1',
      occurred_at: '2026-07-25T09:00:00Z',
      read_at: null,
      dismissed_at: null,
      snoozed_until: null,
      resolved_at: null,
      desktop_delivered_at: null,
      is_unread: true,
      is_snoozed: false,
    },
    {
      notification_id: 'n2',
      category: 'system',
      kind: 'automation_completed',
      priority: 'info',
      title: 'Morning search finished',
      body: '3 new opportunities found.',
      href: '/automation',
      occurred_at: '2026-07-25T08:05:00Z',
      read_at: null,
      dismissed_at: null,
      snoozed_until: null,
      resolved_at: null,
      desktop_delivered_at: null,
      is_unread: true,
      is_snoozed: false,
    },
  ],
  snoozed: [],
  archived: [
    {
      notification_id: 'n3',
      category: 'application',
      kind: 'follow_up_due',
      priority: 'attention',
      title: 'Follow up with Acme Corp',
      body: 'Application follow-up is overdue.',
      href: '/applications/opp2',
      occurred_at: '2026-07-24T10:00:00Z',
      read_at: '2026-07-24T12:00:00Z',
      dismissed_at: '2026-07-24T12:00:00Z',
      snoozed_until: null,
      resolved_at: null,
      desktop_delivered_at: null,
      is_unread: false,
      is_snoozed: false,
    },
  ],
  desktop_pending: [],
  settings: { desktop_enabled: false, updated_at: '2026-07-25T08:00:00Z' },
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve({ ok: true, data: fakeOverview }),
  }))
})

describe('NotificationInbox', () => {
  it('renders the heading and unread count', () => {
    render(<NotificationInbox initialOverview={fakeOverview} />)
    expect(screen.getByRole('heading', { name: 'Notifications' })).toBeDefined()
    const unreadCount = screen.getByText('unread').closest('.notificationUnreadCount')
    expect(unreadCount).toBeDefined()
    expect(unreadCount?.textContent).toContain('2')
  })

  it('renders inbox notification rows', () => {
    render(<NotificationInbox initialOverview={fakeOverview} />)
    expect(screen.getByRole('button', { name: /Senior Engineer at Example/ })).toBeDefined()
    expect(screen.getByRole('button', { name: /Morning search finished/ })).toBeDefined()
  })

  it('renders empty state when inbox is empty', () => {
    const empty: NotificationOverview = {
      ...fakeOverview,
      inbox: [],
      counts: { ...fakeOverview.counts, unread: 0 },
    }
    render(<NotificationInbox initialOverview={empty} />)
    expect(screen.getByText('Nothing needs attention here.')).toBeDefined()
  })

  it('switches to history view when clicking History tab', async () => {
    const user = userEvent.setup()
    render(<NotificationInbox initialOverview={fakeOverview} />)
    await user.click(screen.getByRole('button', { name: /^History/ }))
    expect(screen.getAllByText('Follow up with Acme Corp').length).toBeGreaterThanOrEqual(1)
  })
})

describe('Dashboard renders', () => {
  it('can render a basic element', () => {
    render(<div data-testid="smoke">Hello</div>)
    expect(screen.getByTestId('smoke')).toHaveTextContent('Hello')
  })
})
