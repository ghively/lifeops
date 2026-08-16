import { test, expect } from '@playwright/test'
import { captureBrowserLogs } from '../../helpers/console'
import { BACKEND_URL, FRONTEND_URL } from '../../helpers/env'

test.describe('Anonymous: landing & infrastructure', () => {
  test('app shell loads with the expected title', async ({ page }) => {
    const cap = captureBrowserLogs(page)
    await page.goto(FRONTEND_URL)
    await expect(page).toHaveTitle(/Knowledge|OS/i)
    cap.detach()
  })

  test('backend /health returns healthy', async ({ request }) => {
    const res = await request.get(`${BACKEND_URL}/health`, {
      failOnStatusCode: false,
    })
    expect(res.status()).toBe(200)
    const body = await res.json().catch(() => ({}))
    expect(body.status || body.ok || 'ok').toBeTruthy()
  })

  test('unknown protected route does not throw an uncaught error', async ({
    page,
  }) => {
    const errors: string[] = []
    page.on('pageerror', (e) => errors.push(e.message))
    await page.goto(`${FRONTEND_URL}/this-route-does-not-exist`)
    await page.waitForLoadState('networkidle').catch(() => {})
    expect(errors).toEqual([])
  })
})
