import { test, expect } from '@playwright/test'
import { captureBrowserLogs } from '../../helpers/console'
import { FRONTEND_URL } from '../../helpers/env'

test.describe('Settings page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/settings`)
    await page.waitForLoadState('networkidle').catch(() => {})
  })

  test('renders without throwing', async ({ page }) => {
    const cap = captureBrowserLogs(page)
    await page.waitForTimeout(500)
    cap.detach()
    expect(cap.logs.filter((l) => l.type === 'pageerror')).toEqual([])
  })

  test('exposes at least one setting control (theme/profile/integration)', async ({
    page,
  }) => {
    const candidates = [
      page.getByRole('button', { name: /save|update|apply/i }).first(),
      page.locator('input, select, [role="switch"], [role="combobox"]').first(),
    ]
    let visible = false
    for (const c of candidates) {
      if (await c.isVisible().catch(() => false)) {
        visible = true
        break
      }
    }
    expect(visible, 'no setting controls visible').toBe(true)
  })

  test('toggling theme (if present) does not throw', async ({ page }) => {
    const errors: string[] = []
    page.on('pageerror', (e) => errors.push(e.message))
    const themeToggle = page
      .getByRole('button', { name: /theme|dark|light/i })
      .or(page.locator('[role="switch"]').first())
      .first()
    if (await themeToggle.isVisible().catch(() => false)) {
      await themeToggle.click().catch(() => {})
      await page.waitForTimeout(400)
    }
    expect(errors).toEqual([])
  })
})
