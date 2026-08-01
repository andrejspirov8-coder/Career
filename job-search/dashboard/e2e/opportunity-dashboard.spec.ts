import { expect, test, type Page } from '@playwright/test'
import {
  opportunityOverviewFixture,
  readyOpportunityId,
  readyRow,
  reviewOpportunityId,
  reviewRow,
} from './fixtures/opportunity-overview'

const dashboardToken = 'e2e-token'

type CapturedAction = {
  action: string
  opportunityId?: string
  applicationUrl?: string
  applicationNotes?: string
  applicationOutcome?: string
  decisionReason?: string
  decisionNote?: string
}

type CapturedJob = {
  url?: string
  text?: string
  title?: string
  company?: string
  location?: string
}

async function mockOpportunityApi(page: Page, actions: CapturedAction[] = [], captures: CapturedJob[] = []) {
  await page.route('**/api/opportunities/overview', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(opportunityOverviewFixture),
    })
  })

  await page.route('**/api/opportunities/actions', async (route) => {
    actions.push(route.request().postDataJSON() as CapturedAction)
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, data: { ok: true } }),
    })
  })

  await page.route('**/api/opportunities/capture', async (route) => {
    captures.push(route.request().postDataJSON() as CapturedJob)
    await route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        data: {
          ok: true,
          opportunity_id: reviewOpportunityId,
          title: 'Captured role',
          company: 'Captured company',
          status: 'review',
          live_status: 'unverified',
          fetched_url: false,
        },
      }),
    })
  })

  await page.route(/\/api\/opportunities\/(opp_e2e_ready|opp_e2e_review)$/, async (route) => {
    const opportunityId = new URL(route.request().url()).pathname.split('/').pop()
    const row = opportunityId === readyOpportunityId ? readyRow : reviewRow
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, data: row }),
    })
  })
}

async function loadFixture(page: Page, actions: CapturedAction[] = [], captures: CapturedJob[] = []) {
  await mockOpportunityApi(page, actions, captures)
  await page.goto('/login?next=/opportunities')
  await page.getByLabel('Dashboard token').fill(dashboardToken)
  await page.getByRole('button', { name: 'Unlock dashboard' }).click()
  await expect(page.getByRole('heading', { name: 'Opportunities' })).toBeVisible()
  await page.getByRole('button', { name: 'Refresh' }).click()
  const dailyQueue = page.getByRole('button', { name: /^Daily Queue\s+\d+$/ })
  await expect(dailyQueue).toBeVisible()
  await dailyQueue.click()
  await expect(page.getByRole('button', { name: /^Pack Ready\s+\d+$/ })).toBeVisible()
}

test('protected opportunity API requires the dashboard token', async ({ request }) => {
  const missing = await request.get('/api/opportunities/overview')
  expect(missing.status()).toBe(401)

  const wrong = await request.get('/api/opportunities/overview', {
    headers: { 'x-career-dashboard-token': 'wrong' },
  })
  expect(wrong.status()).toBe(401)

  const valid = await request.get('/api/opportunities/overview', {
    headers: { 'x-career-dashboard-token': dashboardToken },
  })
  expect(valid.status()).toBe(200)

  const autoApply = await request.post('/api/opportunities/actions', {
    headers: {
      'content-type': 'application/json',
      'x-career-dashboard-token': dashboardToken,
    },
    data: { action: 'auto_apply', opportunityId: readyOpportunityId },
  })
  expect(autoApply.status()).toBe(400)

  const privateCapture = await request.post('/api/opportunities/capture', {
    data: { url: 'https://jobs.example.com/private-role' },
  })
  expect(privateCapture.status()).toBe(401)
  const emptyCapture = await request.post('/api/opportunities/capture', {
    headers: { 'x-career-dashboard-token': dashboardToken },
    data: {},
  })
  expect(emptyCapture.status()).toBe(400)

  const privateSearch = await request.get('/api/search?q=operations')
  expect(privateSearch.status()).toBe(401)
  const shortSearch = await request.get('/api/search?q=x', {
    headers: { 'x-career-dashboard-token': dashboardToken },
  })
  expect(shortSearch.status()).toBe(400)
})

test('opportunity dashboard renders saved views and no auto apply control', async ({ page }) => {
  await loadFixture(page)

  await expect(page.locator('body')).not.toContainText('Unhandled Runtime Error')
  await expect(page.getByRole('button', { name: /^Daily Queue\s+\d+$/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /^New\s+\d+$/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /^Review\s+\d+$/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /^Shortlisted\s+\d+$/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /^Pack Ready\s+\d+$/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /^Applied\s+\d+$/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /^Follow-up\s+\d+$/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /^Closed\s+\d+$/ })).toBeVisible()
  await expect(page.getByText('Daily decision funnel')).toBeVisible()
  await expect(page.getByRole('button', { name: /auto apply/i })).toHaveCount(0)
})

test('opportunity filters and detail panel show evidence and match explanation', async ({ page }) => {
  await loadFixture(page)

  await page.getByText('More queues and filters').click()
  await page.getByLabel('Search').fill('retail')
  await expect(page.getByRole('heading', { name: 'Retail Operations Manager' }).first()).toBeVisible()
  await page.getByLabel('CV').selectOption('luxury-retail')
  await expect(page.getByRole('heading', { name: 'Retail Operations Manager' }).first()).toBeVisible()
  await page.getByLabel('Source').selectOption('manual_inbox')
  await expect(page.getByRole('heading', { name: 'Retail Operations Manager' }).first()).toBeVisible()
  await page.getByLabel('Status').selectOption('apply_ready')
  await expect(page.getByRole('heading', { name: 'Retail Operations Manager' }).first()).toBeVisible()

  const detail = page.locator('.detailPanel')
  await expect(detail.getByRole('heading', { name: 'Retail Operations Manager' })).toBeVisible()
  await expect(detail.getByText('Why this role')).toBeVisible()
  await expect(detail.getByText('Application preparation')).toBeVisible()
  await expect(detail.getByText('Matched retail operations leadership.')).toBeVisible()
})

test('opportunity safe actions send expected payloads', async ({ page }) => {
  const actions: CapturedAction[] = []
  await loadFixture(page, actions)

  const detail = page.locator('.detailPanel')
  await detail.getByRole('button', { name: 'Log application' }).click()
  await expect.poll(() => actions.length).toBe(1)
  expect(actions[0]).toMatchObject({
    action: 'log_application',
    opportunityId: readyOpportunityId,
    applicationUrl: 'https://example.com/jobs/retail-ops',
  })

  await detail.getByText('Close as not suitable').click()
  await detail.getByLabel('Why are you closing it?').selectOption('not_relevant')
  await detail.getByRole('button', { name: 'Close role' }).click()
  await expect.poll(() => actions.length).toBe(2)
  expect(actions[1]).toMatchObject({
    action: 'mark_skipped',
    opportunityId: readyOpportunityId,
    decisionReason: 'not_relevant',
  })

  await page.getByRole('button', { name: /^Review\s+\d+$/ }).click()
  await page.getByRole('heading', { name: 'Company watchlist' }).first().click()
  await expect(page.locator('.detailPanel').getByRole('heading', { name: 'Company watchlist' })).toBeVisible()
  await page.locator('.detailPanel').getByRole('button', { name: 'Shortlist role' }).click()
  await expect.poll(() => actions.length).toBe(3)
  expect(actions[2]).toMatchObject({ action: 'mark_apply_ready', opportunityId: reviewOpportunityId })
})

test('a pasted link is captured without browser-side fetching and filters persist in the URL', async ({ page }) => {
  const captures: CapturedJob[] = []
  await loadFixture(page, [], captures)

  await page.getByText('Capture a job').click()
  await page.getByLabel('Job link').fill('https://jobs.example.com/customer-operations')
  await page.getByLabel(/Job title/).fill('Customer Operations Manager')
  await page.getByRole('textbox', { name: 'Company optional' }).fill('Example')
  await page.getByRole('button', { name: 'Save and match' }).click()
  await expect.poll(() => captures.length).toBe(1)
  expect(captures[0]).toMatchObject({
    url: 'https://jobs.example.com/customer-operations',
    title: 'Customer Operations Manager',
    company: 'Example',
  })
  await expect(page.getByText(/link was not fetched/i)).toBeVisible()

  await page.getByText('More queues and filters').click()
  await page.getByLabel('Search').fill('retail')
  await expect(page).toHaveURL(/q=retail/)
})
