import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:3012',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'npm run build && npm run start -- --port 3012',
    url: 'http://127.0.0.1:3012/recruiters',
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      CAREER_DASHBOARD_TOKEN: 'e2e-token',
      CAREER_DASHBOARD_SESSION_SECRET: 'e2e-dashboard-session-secret-0123456789',
    },
  },
})
