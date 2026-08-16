import { test as setup, expect } from '@playwright/test'
import { ensureTestUser } from './helpers/auth'
import { AUTH_STORAGE_PATH, FRONTEND_URL, TEST_USER } from './helpers/env'
import { existsSync, mkdirSync } from 'node:fs'
import { dirname } from 'node:path'

/**
 * Idempotent setup: register a known user (ignoring "already exists"), log in
 * through the UI, and persist the storage state so authenticated specs can
 * pick up the session without each one re-logging in.
 *
 * Failure here cascades — if the backend is unreachable, every authenticated
 * spec will skip rather than spam false negatives.
 */
setup('register and authenticate test user', async ({ page }) => {
  const dir = dirname(AUTH_STORAGE_PATH)
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true })

  const ok = await ensureTestUser()
  expect(ok, 'backend reachable for registration').toBe(true)

  await page.goto(`${FRONTEND_URL}/login`, { waitUntil: 'domcontentloaded' })

  const emailField = page.locator('input[type="email"]').first()
  const passwordField = page.locator('input[type="password"]').first()
  await expect(emailField).toBeVisible()
  await emailField.fill(TEST_USER.email)
  await passwordField.fill(TEST_USER.password)

  const submit = page
    .getByRole('button', { name: /sign in|log in/i })
    .first()
  await submit.click()

  // Either we land on the protected app, or an obvious error appears.
  await page.waitForURL((url) => !url.pathname.startsWith('/login'), {
    timeout: 15_000,
  })

  await page.context().storageState({ path: AUTH_STORAGE_PATH })
})
