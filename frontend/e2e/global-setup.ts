import { chromium, type FullConfig } from '@playwright/test'

const BASE = 'http://localhost:3010'
const API = 'http://localhost:8010/api/v1'
const TEST_EMAIL = 'e2ewalk@test.com'
const TEST_PASSWORD = 'password123'

async function globalSetup(config: FullConfig) {
  // Ensure test user exists
  await fetch(`${API}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: TEST_EMAIL, username: 'e2ewalk', password: TEST_PASSWORD }),
  }).catch(() => {})

  // Login and save storage state
  const browser = await chromium.launch()
  const context = await browser.newContext()
  const page = await context.newPage()

  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(500)
  await page.locator('input[type="email"]').fill(TEST_EMAIL)
  await page.locator('input[type="password"]').fill(TEST_PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.waitForTimeout(3000)

  await context.storageState({ path: 'e2e/.auth-storage.json' })
  await browser.close()
}

export default globalSetup
