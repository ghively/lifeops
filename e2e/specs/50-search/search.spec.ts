import { test, expect } from '@playwright/test'
import { captureBrowserLogs } from '../../helpers/console'
import { FRONTEND_URL } from '../../helpers/env'

test.describe('Search page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/search`)
    await page.waitForLoadState('networkidle').catch(() => {})
  })

  test('renders the search input', async ({ page }) => {
    const cap = captureBrowserLogs(page)
    const input = page
      .getByPlaceholder(/search/i)
      .or(page.locator('input[type="search"]'))
      .first()
    await expect(input).toBeVisible({ timeout: 10_000 })
    cap.detach()
  })

  test('submitting a query does not throw', async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', (e) => errors.push(e.message))

    const input = page
      .getByPlaceholder(/search/i)
      .or(page.locator('input[type="search"]'))
      .first()
    if (!(await input.isVisible().catch(() => false))) {
      test.skip(true, 'no search input visible')
    }
    await input.fill('knowledge')
    await input.press('Enter')
    await page.waitForTimeout(2000)
    expect(errors).toEqual([])
  })
})
