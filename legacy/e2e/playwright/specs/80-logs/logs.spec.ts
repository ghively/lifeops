import { test, expect } from '@playwright/test'
import { captureBrowserLogs } from '../../helpers/console'
import { FRONTEND_URL } from '../../helpers/env'

test.describe('Logs page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/logs`)
    await page.waitForLoadState('networkidle').catch(() => {})
  })

  test('renders without throwing', async ({ page }) => {
    const cap = captureBrowserLogs(page)
    await page.waitForTimeout(500)
    cap.detach()
    expect(cap.logs.filter((l) => l.type === 'pageerror')).toEqual([])
  })

  test('shows log content area', async ({ page }) => {
    // Be permissive about layout — accept a table, list, or pre.
    const surface = page.locator('table, ul, pre, [role="log"]').first()
    expect(await surface.count()).toBeGreaterThan(0)
  })
})
