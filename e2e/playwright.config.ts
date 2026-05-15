import { defineConfig, devices } from '@playwright/test'

const FRONTEND_URL = process.env.E2E_FRONTEND_URL || 'http://localhost:5173'

export default defineConfig({
  testDir: './specs',
  // Tests are independent — keep one failing spec from masking others.
  fullyParallel: false,
  workers: 1,
  // Don't bail. We want every spec to run so the report is complete.
  maxFailures: 0,
  forbidOnly: !!process.env.CI,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [
    ['list'],
    ['html', { open: 'never', outputFolder: 'playwright-report' }],
    ['json', { outputFile: 'playwright-report/results.json' }],
  ],
  outputDir: 'test-results',
  use: {
    baseURL: FRONTEND_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
  },
  projects: [
    {
      name: 'setup',
      testDir: '.',
      testMatch: /global-setup\.spec\.ts/,
    },
    {
      name: 'chromium-anon',
      testDir: './specs/00-anonymous',
      use: { ...devices['Desktop Chrome'] },
      dependencies: ['setup'],
    },
    {
      name: 'chromium-auth',
      testDir: './specs',
      testIgnore: /00-anonymous/,
      use: {
        ...devices['Desktop Chrome'],
        storageState: 'fixtures/.auth-storage.json',
      },
      dependencies: ['setup'],
    },
  ],
})
