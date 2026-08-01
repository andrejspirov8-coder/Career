import { expect, test } from '@playwright/test'

import type { CareerNotification, NotificationOverview } from '../lib/notification-types'
import { opportunityOverviewFixture } from './fixtures/opportunity-overview'

const dashboardToken = 'e2e-token'

test('automation, notification, CV, and development-agent APIs stay private and non-cacheable', async ({ request }) => {
  for (const path of ['/api/automation/overview', '/api/dev-agents/overview', '/api/notifications/overview', '/api/cvs/overview', '/api/cvs/studio/business-process-operations', '/api/preferences', '/api/applications/overview', '/api/settings/overview', '/api/insights/overview', '/api/ai/status']) {
    const unauthenticated = await request.get(path)
    expect(unauthenticated.status()).toBe(401)

    const authenticated = await request.get(path, {
      headers: { 'x-career-dashboard-token': dashboardToken },
    })
    expect(authenticated.status()).toBe(200)
    expect(authenticated.headers()['cache-control']).toContain('no-store')
    expect(authenticated.headers()['x-content-type-options']).toBe('nosniff')
    await expect(authenticated.json()).resolves.toMatchObject({ ok: true })
  }

  const invalidRun = await request.get('/api/automation/runs/not-a-run-id', {
    headers: { 'x-career-dashboard-token': dashboardToken },
  })
  expect(invalidRun.status()).toBe(400)

  const invalidAgentRun = await request.get('/api/dev-agents/runs/not-an-agent-id', {
    headers: { 'x-career-dashboard-token': dashboardToken },
  })
  expect(invalidAgentRun.status()).toBe(400)

  const unknownCv = await request.get('/api/cvs/not-a-variant/visual', {
    headers: { 'x-career-dashboard-token': dashboardToken },
  })
  expect(unknownCv.status()).toBe(404)

  const cvPreview = await request.get('/api/cvs/business-process-operations/visual', {
    headers: { 'x-career-dashboard-token': dashboardToken },
  })
  expect(cvPreview.status()).toBe(200)
  expect(cvPreview.headers()['content-type']).toBe('application/pdf')
  expect(cvPreview.headers()['x-frame-options']).toBe('SAMEORIGIN')
  expect(cvPreview.headers()['content-security-policy']).toContain("frame-ancestors 'self'")

  const privateExport = await request.get('/api/export')
  expect(privateExport.status()).toBe(401)
  const exportResponse = await request.get('/api/export', {
    headers: { 'x-career-dashboard-token': dashboardToken },
  })
  expect(exportResponse.status()).toBe(200)
  expect(exportResponse.headers()['content-disposition']).toContain('career-data-')
  expect(exportResponse.headers()['cache-control']).toContain('no-store')

  const privateCalendar = await request.get('/api/applications/calendar')
  expect(privateCalendar.status()).toBe(401)
  const calendar = await request.get('/api/applications/calendar', {
    headers: { 'x-career-dashboard-token': dashboardToken },
  })
  expect(calendar.status()).toBe(200)
  expect(calendar.headers()['content-type']).toContain('text/calendar')

  const privateApplicationAction = await request.post('/api/applications/actions', {
    data: { action: 'save_entry' },
  })
  expect(privateApplicationAction.status()).toBe(401)

  const privateDraft = await request.post('/api/ai/draft', {
    data: { opportunityId: 'opp_private', draftType: 'cover_letter', instructions: '' },
  })
  expect(privateDraft.status()).toBe(401)

  const privateCvEdit = await request.post('/api/cvs/studio/business-process-operations', {
    data: { action: 'rebuild_selected' },
  })
  expect(privateCvEdit.status()).toBe(401)

  const privateNotificationAction = await request.post('/api/notifications/actions', {
    data: { action: 'read_all' },
  })
  expect(privateNotificationAction.status()).toBe(401)

  const privateAgentAction = await request.post('/api/dev-agents/actions', {
    data: { action: 'start', objective: 'Run anything' },
  })
  expect(privateAgentAction.status()).toBe(401)

  const invalidAgentAction = await request.post('/api/dev-agents/actions', {
    headers: { 'x-career-dashboard-token': dashboardToken },
    data: { action: 'run_command', command: 'open the shell' },
  })
  expect(invalidAgentAction.status()).toBe(400)

  const invalidNotificationAction = await request.post('/api/notifications/actions', {
    headers: { 'x-career-dashboard-token': dashboardToken },
    data: { action: 'run_command' },
  })
  expect(invalidNotificationAction.status()).toBe(400)

  const invalidCvAction = await request.post('/api/cvs/studio/business-process-operations', {
    headers: { 'x-career-dashboard-token': dashboardToken },
    data: { action: 'run_command', command: 'rm -rf output' },
  })
  expect(invalidCvAction.status()).toBe(400)
})

test('the local control center exposes safe automation, CV, and recruiter workflows', async ({ page }) => {
  const loginResponse = await page.goto('/login?next=/automation')
  expect(loginResponse?.headers()['cache-control']).toMatch(/no-store|no-cache/)
  expect(loginResponse?.headers()['content-security-policy']).toContain("object-src 'none'")
  expect(loginResponse?.headers()['content-security-policy']).not.toContain("'unsafe-eval'")
  expect(loginResponse?.headers()['x-frame-options']).toBe('DENY')

  await page.getByLabel('Dashboard token').fill(dashboardToken)
  await page.getByRole('button', { name: 'Unlock dashboard' }).click()

  await expect(page).toHaveURL(/\/automation$/)
  await expect(page.getByRole('heading', { name: 'Automation' })).toBeVisible()
  await expect(page.getByText('Daily work', { exact: true })).toBeVisible()
  await expect(page.getByText('Manage', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: /Run today's search/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /Rebuild all CVs/ })).toBeVisible()
  await expect(page.getByText('Read-only LinkedIn jobs')).toBeVisible()
  await expect(page.getByText(/LinkedIn review remains manual/)).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Can the search see fresh jobs?' })).toBeVisible()

  await page.getByRole('link', { name: 'Development Agents', exact: true }).click()
  await expect(page).toHaveURL(/\/dev-agents$/)
  await expect(page.getByRole('heading', { name: 'Development Agents' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Queue local work' })).toBeVisible()
  await expect(
    page.getByText('No free-form shell commands, installs, Git actions, or online fallback.'),
  ).toBeVisible()

  await page.getByRole('link', { name: /Notifications/ }).click()
  await expect(page).toHaveURL(/\/notifications$/)
  await expect(page.getByRole('heading', { name: 'Notifications' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Show important updates on this Mac' })).toBeVisible()

  await page.getByRole('link', { name: 'CV Studio', exact: true }).click()
  await expect(page).toHaveURL(/\/cvs(?:\?|$)/)
  await expect(page.getByRole('heading', { name: 'CV Studio' })).toBeVisible()
  await expect(page.locator('.variantRow')).toHaveCount(6)
  await expect(page.getByRole('heading', { name: 'Edit by section' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Check this CV against a role' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Visual and ATS preview' })).toBeVisible()
  await expect(page.locator('.cvPreviewDocument iframe')).toHaveCount(2)
  await expect(page.getByRole('button', { name: /Rebuild selected only/ })).toBeVisible()

  await page.getByRole('link', { name: 'Applications' }).click()
  await expect(page).toHaveURL(/\/applications/)
  await expect(page.getByRole('heading', { name: 'Applications', exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Add dates to calendar' })).toBeVisible()

  await page.getByRole('link', { name: 'Insights' }).click()
  await expect(page).toHaveURL(/\/insights/)
  await expect(page.getByRole('heading', { name: 'Insights' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Where applications are progressing' })).toBeVisible()

  await page.getByRole('link', { name: 'Recruiters' }).click()
  await expect(page).toHaveURL(/\/recruiters$/)
  await expect(page.getByRole('heading', { name: 'Recruiters' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'LinkedIn stays manual' })).toBeVisible()
  await expect(page.getByRole('button', { name: /Search \+ Rank/i })).toHaveCount(0)
  await expect(page.getByRole('button', { name: /Dispatch/i })).toHaveCount(0)

  await page.getByRole('link', { name: 'Settings' }).click()
  await expect(page).toHaveURL(/\/settings$/)
  await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Tell the app what good looks like' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Secure local storage' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Encrypted workspace backup' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Local drafting' })).toBeVisible()
  await expect(page.getByText('make dashboard-start')).toBeVisible()

  await page.getByRole('link', { name: 'Today', exact: true }).click()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByText('Daily routine', { exact: true })).toBeVisible()
})

test('notification inbox supports safe read and snooze actions', async ({ page }) => {
  const urgentId = `notification_${'1'.repeat(32)}`
  const roleId = `notification_${'2'.repeat(32)}`
  const actions: Array<{ action?: string; notificationId?: string }> = []
  let inbox: CareerNotification[] = [
    {
      notification_id: urgentId,
      category: 'application',
      kind: 'application_deadline',
      priority: 'urgent',
      title: 'Application deadline tomorrow',
      body: 'Operations Manager at Example. Review the application plan before the deadline.',
      href: '/applications?opportunity=opp_deadline',
      occurred_at: '2026-07-15T07:30:00Z',
      read_at: null,
      dismissed_at: null,
      snoozed_until: null,
      resolved_at: null,
      desktop_delivered_at: null,
      is_unread: true,
      is_snoozed: false,
    },
    {
      notification_id: roleId,
      category: 'opportunity',
      kind: 'strong_role',
      priority: 'attention',
      title: 'Strong role ready to review',
      body: 'Retail Operations Manager at Example · match 27.0.',
      href: '/opportunities?opportunity=opp_role',
      occurred_at: '2026-07-15T07:00:00Z',
      read_at: null,
      dismissed_at: null,
      snoozed_until: null,
      resolved_at: null,
      desktop_delivered_at: null,
      is_unread: true,
      is_snoozed: false,
    },
  ]
  let snoozed: CareerNotification[] = []

  const overview = (): NotificationOverview => ({
    schema: 'career_notification_overview_v1',
    generated_at: '2026-07-15T09:00:00Z',
    counts: {
      active: inbox.length + snoozed.length,
      unread: inbox.filter((item) => item.is_unread).length,
      urgent: inbox.filter((item) => item.priority === 'urgent').length,
      attention: inbox.filter((item) => item.priority === 'attention').length,
      snoozed: snoozed.length,
      archived: 0,
    },
    inbox,
    snoozed,
    archived: [],
    desktop_pending: [],
    settings: { desktop_enabled: false, updated_at: '2026-07-15T09:00:00Z' },
  })

  await page.route('**/api/notifications/overview*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, data: overview() }),
    })
  })
  await page.route('**/api/notifications/actions', async (route) => {
    const body = route.request().postDataJSON() as { action?: string; notificationId?: string }
    actions.push(body)
    if (body.action === 'read' && body.notificationId) {
      inbox = inbox.map((item) => item.notification_id === body.notificationId
        ? { ...item, is_unread: false, read_at: '2026-07-15T09:00:01Z' }
        : item)
    }
    if (body.action === 'snooze_day' && body.notificationId) {
      const item = inbox.find((candidate) => candidate.notification_id === body.notificationId)
      inbox = inbox.filter((candidate) => candidate.notification_id !== body.notificationId)
      if (item) {
        snoozed = [{
          ...item,
          is_snoozed: true,
          snoozed_until: '2026-07-16T09:00:00Z',
        }, ...snoozed]
      }
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, data: overview() }),
    })
  })

  await page.goto('/login?next=/notifications')
  await page.getByLabel('Dashboard token').fill(dashboardToken)
  await page.getByRole('button', { name: 'Unlock dashboard' }).click()
  await expect(page.getByRole('button', { name: /Application deadline tomorrow/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /Strong role ready to review/ })).toBeVisible()

  await page.getByRole('button', { name: /Application deadline tomorrow/ }).click()
  await expect.poll(() => actions).toContainEqual({ action: 'read', notificationId: urgentId })
  await page.getByRole('button', { name: 'Snooze 1 day' }).click()
  await expect.poll(() => actions).toContainEqual({ action: 'snooze_day', notificationId: urgentId })

  await page.getByRole('button', { name: /Snoozed 1/ }).click()
  await expect(page.getByRole('heading', { name: 'Application deadline tomorrow' })).toBeVisible()
  await expect(page.getByText('Snoozed until 16 Jul 2026')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Enable desktop alerts' })).toBeVisible()
})

test('CV Studio edits one section, rebuilds one variant, and compares a saved job', async ({ page }) => {
  const actions: Array<{ action?: string; content?: string }> = []
  await page.route('**/api/opportunities/overview', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(opportunityOverviewFixture),
    })
  })
  await page.route('**/api/cvs/studio/business-process-operations', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.continue()
      return
    }
    const body = route.request().postDataJSON() as { action?: string; content?: string }
    actions.push(body)
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        data: {
          changed: true,
          saved_version: {
            version_id: '20260715T020000Z-abcdef123456',
            created_at: '2026-07-15T02:00:00Z',
            reason: 'before_save',
            content_hash: 'a'.repeat(64),
            character_count: 2000,
            word_count: 300,
          },
          document: {
            schema: 'career_cv_studio_v1',
            variant: 'business-process-operations',
            source_filename: 'andrej-spirov-cv-business-process-operations.md',
            content: body.content,
            content_hash: 'b'.repeat(64),
            source_updated_at: '2026-07-15T02:00:01Z',
            versions: [{
              version_id: '20260715T020000Z-abcdef123456',
              created_at: '2026-07-15T02:00:00Z',
              reason: 'before_save',
              content_hash: 'a'.repeat(64),
              character_count: 2000,
              word_count: 300,
            }],
          },
          build: {
            variant: 'business-process-operations',
            visual_pdf: { filename: 'visual.pdf', size_bytes: 1000, updated_at: '2026-07-15T02:00:01Z' },
            ats_pdf: { filename: 'ats.pdf', size_bytes: 1000, updated_at: '2026-07-15T02:00:01Z' },
            canva_text: { filename: 'canva.txt', size_bytes: 1000, updated_at: '2026-07-15T02:00:01Z' },
          },
        },
      }),
    })
  })
  await page.route(/\/api\/cvs\/studio\/business-process-operations\/compare\?opportunity=/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        data: {
          schema: 'career_cv_job_comparison_v1',
          variant: 'business-process-operations',
          opportunity: {
            opportunity_id: 'opp_cv_compare',
            title: 'Customer Operations Manager',
            company: 'Example',
            location: 'Vilnius',
          },
          score: 21,
          tie_break_score: 0.2,
          rank: 1,
          variant_count: 6,
          keyword_hits: ['customer operations', 'reporting'],
          negative_hits: [],
          keyword_gaps: [{ keyword: 'implementation', count: 3 }],
          gap_notes: [],
          recommended_variant: 'business-process-operations',
          is_recommended: true,
          confidence: 'clear_winner',
        },
      }),
    })
  })

  await page.goto('/login?next=/cvs?variant=business-process-operations')
  await page.getByLabel('Dashboard token').fill(dashboardToken)
  await page.getByRole('button', { name: 'Unlock dashboard' }).click()
  await expect(page.getByRole('heading', { name: 'CV Studio' })).toBeVisible()

  const summary = page.getByLabel('Professional Summary')
  await expect(summary).toBeEnabled()
  await summary.fill(`${await summary.inputValue()} Added for a safe browser test.`)
  await page.getByRole('button', { name: /Save & rebuild this CV/ }).click()
  await expect.poll(() => actions.length).toBe(1)
  expect(actions[0].action).toBe('save_rebuild')
  expect(actions[0].content).toContain('Added for a safe browser test.')
  await expect(page.getByText(/previous source is available below/i)).toBeVisible()
  await expect(page.getByText('Before edit')).toBeVisible()

  const opportunityPicker = page.getByLabel('Opportunity')
  await expect(opportunityPicker.locator('option')).toHaveCount(3)
  await opportunityPicker.selectOption({ index: 1 })
  await expect(page.getByText('Possible wording gaps')).toBeVisible()
  await expect(page.locator('.cvGapList')).toContainText('implementation')
  await expect(page.getByText('Recommended CV', { exact: true })).toBeVisible()
})

test('global search links directly to a matching workspace item', async ({ page }) => {
  await page.route(/\/api\/search\?q=/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        data: {
          query: 'retail',
          results: [{
            kind: 'opportunity',
            id: 'opp_search_result',
            title: 'Retail Operations Manager',
            subtitle: 'Example · Vilnius',
            href: '/opportunities?opportunity=opp_search_result&view=stage_review',
          }],
        },
      }),
    })
  })
  await page.goto('/login')
  await page.getByLabel('Dashboard token').fill(dashboardToken)
  await page.getByRole('button', { name: 'Unlock dashboard' }).click()
  await page.getByLabel('Find anything').fill('retail')
  await expect(page.getByRole('link', { name: /Retail Operations Manager/ })).toHaveAttribute(
    'href',
    '/opportunities?opportunity=opp_search_result&view=stage_review',
  )
})
