import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: [['html', { open: 'never' }], ['list']],
  timeout: 60_000,
  outputDir: './e2e/screenshots',
  globalSetup: './e2e/global-setup.ts',
  use: {
    baseURL: 'http://localhost:3010',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'off',
  },
  projects: [
    // Auth tests — no stored session (test the login flow itself)
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
      testMatch: /auth\.spec/,
    },
    // App feature tests — use stored session (no login needed per test)
    {
      name: 'chromium-auth',
      use: {
        browserName: 'chromium',
        storageState: 'e2e/.auth-storage.json',
      },
      testMatch: /app-features\.spec/,
    },
  ],
})
