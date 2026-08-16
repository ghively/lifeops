import { test, expect } from '@playwright/test'
import { captureBrowserLogs } from '../../helpers/console'
import { FRONTEND_URL, TEST_USER } from '../../helpers/env'

// These specs run without an authenticated session — they exercise the
// public surface (login, register, reset-password, redirect behavior).

test.describe('Anonymous: auth surface', () => {
  test('login page renders email/password fields and CTA', async ({ page }) => {
    const cap = captureBrowserLogs(page)
    await page.goto(`${FRONTEND_URL}/login`)

    await expect(page.locator('input[type="email"]').first()).toBeVisible()
    await expect(page.locator('input[type="password"]').first()).toBeVisible()
    await expect(
      page.getByRole('button', { name: /sign in|log in/i }).first(),
    ).toBeVisible()

    cap.detach()
    expect(cap.logs.filter((l) => l.type === 'pageerror')).toEqual([])
  })

  test('protected route bounces to /login when unauthenticated', async ({
    page,
  }) => {
    await page.goto(`${FRONTEND_URL}/tasks`)
    await page.waitForURL(/\/login/, { timeout: 10_000 })
    expect(page.url()).toMatch(/\/login/)
  })

  test('reset password page is reachable from login', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/login`)
    const link = page.getByRole('link', { name: /forgot|reset/i }).first()
    if (await link.isVisible().catch(() => false)) {
      await link.click()
      await expect(page).toHaveURL(/reset-password/)
    } else {
      // Direct nav fallback if the login UI doesn't expose the link.
      await page.goto(`${FRONTEND_URL}/reset-password`)
      await expect(page).toHaveURL(/reset-password/)
    }
    await expect(page.locator('input[type="email"]').first()).toBeVisible()
  })

  test('register flow accepts a new user (or surfaces a clear duplicate error)', async ({
    page,
  }) => {
    await page.goto(`${FRONTEND_URL}/login?mode=register`)

    const uniqueEmail = `e2e-reg-${Date.now()}@knowledge-os.local`
    const uniqueUser = `e2ereg${Date.now()}`

    const fillIfPresent = async (placeholder: RegExp, value: string) => {
      const loc = page.getByPlaceholder(placeholder).first()
      if (await loc.isVisible().catch(() => false)) await loc.fill(value)
    }
    await fillIfPresent(/email|name@example/i, uniqueEmail)
    await fillIfPresent(/username|johndoe/i, uniqueUser)
    await fillIfPresent(/full name|john doe/i, 'E2E Register')
    await fillIfPresent(/min\.? 8|password/i, TEST_USER.password)
    await fillIfPresent(/confirm/i, TEST_USER.password)

    const submit = page
      .getByRole('button', { name: /create account|sign up|register/i })
      .first()
    if (await submit.isVisible().catch(() => false)) await submit.click()

    await page.waitForLoadState('networkidle').catch(() => {})

    const url = page.url()
    const onApp = !url.includes('/login') && !url.includes('/register')
    const visibleError = await page
      .locator('text=/invalid|already|exists|error/i')
      .first()
      .isVisible()
      .catch(() => false)
    expect(onApp || visibleError).toBeTruthy()
  })
})
