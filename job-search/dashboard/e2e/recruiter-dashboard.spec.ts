import { expect, test, type Page } from '@playwright/test'
import {
  autoSendProfileUrl,
  recruiterOverviewFixture,
  reviewProfileUrl,
} from './fixtures/recruiter-overview'

const dashboardToken = 'e2e-token'

type CapturedAction = {
  action: string
  profileUrl?: string
  profileUrls?: string[]
  note?: string
}

async function mockRecruiterApi(page: Page, actions: CapturedAction[] = []) {
  await page.route('**/api/recruiter/overview', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(recruiterOverviewFixture),
    })
  })

  await page.route('**/api/recruiter/actions', async (route) => {
    actions.push(route.request().postDataJSON() as CapturedAction)
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, data: { ok: true } }),
    })
  })
}

async function loadFixtureOverview(page: Page, actions: CapturedAction[] = []) {
  await mockRecruiterApi(page, actions)
  await page.goto('/login?next=/recruiters')
  await page.getByLabel('Dashboard token').fill(dashboardToken)
  await expect(page.getByRole('checkbox', { name: /Remember this browser for 30 days/ })).toBeChecked()
  await page.getByRole('button', { name: 'Unlock dashboard' }).click()
  await expect(page.getByRole('heading', { name: 'Recruiters' })).toBeVisible()
  await page.getByText('Refresh or re-rank saved recruiter data').click()
  await page.getByRole('button', { name: 'Refresh' }).click()
  await expect(page.getByRole('button', { name: 'Needs Review (1)' })).toBeVisible()
  await page.getByRole('button', { name: 'Needs Review (1)' }).click()
  await expect(page.getByRole('heading', { name: 'Avery Review' }).first()).toBeVisible()
  await page.getByRole('button', { name: /Select Avery Review/ }).click()
  await expect(page.locator('.detailPanel').getByRole('heading', { name: 'Avery Review' })).toBeVisible()
}

test('dashboard pages require login and logout clears the protected session', async ({ page, request }) => {
  await page.goto('/recruiters')
  await expect(page).toHaveURL(/\/login\?next=%2Frecruiters/)
  await expect(page.getByRole('heading', { name: 'Career Dashboard' })).toBeVisible()
  await expect(page.locator('body')).not.toContainText('Follow up first')

  const crossOriginLogin = await request.post('/api/auth/login', {
    headers: { origin: 'https://attacker.example' },
    data: { token: dashboardToken },
  })
  expect(crossOriginLogin.status()).toBe(403)

  const wrongLogin = await request.post('/api/auth/login', {
    headers: { origin: 'http://127.0.0.1:3012' },
    data: { token: 'wrong-token' },
  })
  expect(wrongLogin.status()).toBe(401)

  await page.getByLabel('Dashboard token').fill(dashboardToken)
  await page.getByRole('button', { name: 'Unlock dashboard' }).click()
  await expect(page.getByRole('heading', { name: 'Recruiters' })).toBeVisible()
  const sbCookie = (await page.context().cookies()).find((cookie) => cookie.name === 'career_sb_token')
  expect(sbCookie?.httpOnly).toBe(true)
  expect(sbCookie?.sameSite).toBe('Strict')
  expect(sbCookie?.value).toBe(dashboardToken)
  expect(sbCookie?.expires || 0).toBeGreaterThan(Date.now() / 1000 + 29 * 24 * 60 * 60)

  await page.getByRole('button', { name: 'Lock dashboard' }).click()
  await expect(page).toHaveURL(/\/login$/)
  await page.goto('/recruiters')
  await expect(page).toHaveURL(/\/login\?next=%2Frecruiters/)
})

test('protected recruiter API requires the dashboard token', async ({ request }) => {
  const missingToken = await request.get('/api/recruiter/overview')
  expect(missingToken.status()).toBe(401)

  const wrongToken = await request.get('/api/recruiter/overview', {
    headers: { 'x-career-dashboard-token': 'wrong-token' },
  })
  expect(wrongToken.status()).toBe(401)

  const validToken = await request.get('/api/recruiter/overview', {
    headers: { 'x-career-dashboard-token': dashboardToken },
  })
  expect(validToken.status()).toBe(200)
  await expect(validToken).toBeOK()

  const bulkApproval = await request.post('/api/recruiter/actions', {
    headers: {
      'content-type': 'application/json',
      'x-career-dashboard-token': dashboardToken,
    },
    data: { action: 'bulk_approve_note', profileUrls: [reviewProfileUrl] },
  })
  expect(bulkApproval.status()).toBe(400)
  await expect(bulkApproval).not.toBeOK()
  await expect(bulkApproval.json()).resolves.toMatchObject({
    ok: false,
    error: 'Bulk approval is not supported from the dashboard.',
  })

  const blockedAutomation = await request.post('/api/recruiter/actions', {
    headers: {
      'content-type': 'application/json',
      'x-career-dashboard-token': dashboardToken,
    },
    data: { action: 'dispatch_dry_run' },
  })
  expect(blockedAutomation.status()).toBe(400)
  await expect(blockedAutomation.json()).resolves.toMatchObject({
    ok: false,
    error: 'Unsupported dashboard action.',
  })
})

test('recruiter workspace renders saved views and keeps LinkedIn work manual', async ({ page }) => {
  await loadFixtureOverview(page)

  await expect(page.locator('body')).not.toContainText('Unhandled Runtime Error')
  await expect(page.getByRole('button', { name: 'Follow Up (1)' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Ready To Contact (1)' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Needs Review (1)' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Skipped (1)' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Sent Archive (1)' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Risk Flags (2)' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'LinkedIn stays manual' })).toBeVisible()
  await expect(page.getByText(/The web app cannot search or send/)).toBeVisible()
  await expect(page.getByText('Hard daily ceiling', { exact: true })).toBeVisible()
  await expect(page.getByText('Ready for manual send')).toBeVisible()
  await expect(page.getByRole('button', { name: /Search \+ Rank/i })).toHaveCount(0)
  await expect(page.getByRole('button', { name: /Dispatch Preview/i })).toHaveCount(0)
  await expect(page.getByRole('button', { name: /live send/i })).toHaveCount(0)
  await expect(page.getByRole('button', { name: /bulk approve/i })).toHaveCount(0)
})

test('saved-view filters cover search, persona, CV, risk, and approval state', async ({ page }) => {
  await loadFixtureOverview(page)

  await expect(page.getByRole('heading', { name: 'Avery Review' }).first()).toBeVisible()
  await page.getByLabel('Search').fill('pipeline')
  await expect(page.getByRole('heading', { name: 'Avery Review' }).first()).toBeVisible()
  await page.getByLabel('Search').fill('no matching profile')
  await expect(page.getByText('No rows match this view.')).toBeVisible()

  await page.getByLabel('Search').fill('')
  await page.getByLabel('Persona').selectOption('recruiter_hr')
  await expect(page.getByRole('heading', { name: 'Avery Review' }).first()).toBeVisible()
  await page.getByLabel('CV').selectOption('operations-management')
  await expect(page.getByRole('heading', { name: 'Avery Review' }).first()).toBeVisible()
  await page.getByLabel('Risk').selectOption('low_confidence')
  await expect(page.getByRole('heading', { name: 'Avery Review' }).first()).toBeVisible()
  await page.getByLabel('Approval').selectOption('not_approved')
  await expect(page.getByRole('heading', { name: 'Avery Review' }).first()).toBeVisible()

  await page.getByRole('button', { name: 'Ready To Contact (1)' }).click()
  await page.getByLabel('Persona').selectOption('all')
  await page.getByLabel('CV').selectOption('all')
  await page.getByLabel('Risk').selectOption('all')
  await page.getByLabel('Approval').selectOption('approved')
  await expect(page.getByRole('heading', { name: 'Blake Auto' }).first()).toBeVisible()
})

test('profile detail shows note context and safe single-profile action payloads', async ({ page }) => {
  const actions: CapturedAction[] = []
  await loadFixtureOverview(page, actions)

  const detail = page.locator('.detailPanel')
  await expect(detail.getByRole('heading', { name: 'Avery Review' })).toBeVisible()
  await expect(detail.getByText('Score Breakdown')).toBeVisible()
  await expect(detail.getByText('Evidence')).toBeVisible()
  await expect(detail.getByText('Next Action')).toBeVisible()
  await expect(detail.getByText('Note Quality')).toBeVisible()
  await expect(detail.getByText('missing_matching_approval')).toBeVisible()
  await expect(detail.getByText('reviewhash')).toBeVisible()
  await expect(detail.getByText('mark_review')).toBeVisible()
  await expect(detail.getByText('skip:skip -> queue_review:review')).toBeVisible()

  const updatedNote = 'Hi Avery, updated e2e note for review.'
  await detail.locator('textarea').fill(updatedNote)
  await detail.getByRole('button', { name: 'Save Edited Note' }).click()
  await expect.poll(() => actions.length).toBe(1)
  expect(actions[0]).toEqual({ action: 'update_note', profileUrl: reviewProfileUrl, note: updatedNote })

  await detail.getByRole('button', { name: 'Approve Note' }).click()
  await expect.poll(() => actions.length).toBe(2)
  expect(actions[1]).toEqual({ action: 'approve_note', profileUrl: reviewProfileUrl, note: updatedNote })

  await detail.getByRole('button', { name: 'Mark Skipped' }).click()
  await expect.poll(() => actions.length).toBe(3)
  expect(actions[2]).toEqual({ action: 'mark_skipped', profileUrl: reviewProfileUrl })

  await detail.getByRole('button', { name: 'Move To Review' }).click()
  await expect.poll(() => actions.length).toBe(4)
  expect(actions[3]).toEqual({ action: 'mark_review', profileUrl: reviewProfileUrl })

  await detail.getByRole('button', { name: 'Copy Note' }).click()
  await expect.poll(() => actions.length).toBe(5)
  expect(actions[4]).toEqual({ action: 'copy_note_recorded', profileUrl: reviewProfileUrl, note: updatedNote })

  await detail.getByRole('button', { name: 'Mark Sent Manually' }).click()
  await expect.poll(() => actions.length).toBe(6)
  expect(actions[5]).toEqual({ action: 'mark_sent_manual', profileUrl: reviewProfileUrl, note: updatedNote })
})

test('bulk skip and review actions send selected profile URLs only', async ({ page }) => {
  const actions: CapturedAction[] = []
  await loadFixtureOverview(page, actions)

  const bulkBar = page.locator('.bulkBar')
  await bulkBar.getByLabel('Select visible').check()
  await bulkBar.getByRole('button', { name: 'Mark Skipped' }).click()
  await expect.poll(() => actions.length).toBe(1)
  expect(actions[0]).toEqual({ action: 'bulk_mark_skipped', profileUrls: [reviewProfileUrl] })

  const selectVisible = bulkBar.getByLabel('Select visible')
  await expect(selectVisible).toBeEnabled()
  await expect(selectVisible).not.toBeChecked()
  await selectVisible.check()
  await bulkBar.getByRole('button', { name: 'Move To Review' }).click()
  await expect.poll(() => actions.length).toBe(2)
  expect(actions[1]).toEqual({ action: 'bulk_mark_review', profileUrls: [reviewProfileUrl] })

  await expect(selectVisible).toBeEnabled()
  await page.getByRole('button', { name: 'Ready To Contact (1)' }).click()
  await page.getByRole('button', { name: /Select Blake Auto/ }).click()
  await expect(page.locator('.detailPanel').getByRole('heading', { name: 'Blake Auto' })).toBeVisible()
  await expect(page.locator('.detailPanel').getByRole('link', { name: 'Open Profile' })).toHaveAttribute('href', autoSendProfileUrl)
})
