import { test, expect } from '@playwright/test'
import { captureBrowserLogs } from '../../helpers/console'
import { FRONTEND_URL } from '../../helpers/env'

const ROUTES = [
  { path: '/', label: /outliner|knowledge|home/i },
  { path: '/tasks', label: /tasks/i },
  { path: '/files', label: /files/i },
  { path: '/agents', label: /agents/i },
  { path: '/search', label: /search/i },
  { path: '/settings', label: /settings/i },
  { path: '/logs', label: /logs/i },
] as const

test.describe('Navigation: every primary route loads', () => {
  for (const route of ROUTES) {
    test(`${route.path} renders without uncaught errors`, async ({ page }) => {
      const cap = captureBrowserLogs(page)
      await page.goto(`${FRONTEND_URL}${route.path}`, {
        waitUntil: 'domcontentloaded',
      })
      await page.waitForLoadState('networkidle').catch(() => {})
      // We don't assert specific text — pages have different shells.
      // We DO assert: no uncaught exception, page reachable, no auth bounce.
      expect(page.url()).not.toMatch(/\/login/)
      cap.detach()
      const fatal = cap.logs.filter((l) => l.type === 'pageerror')
      expect(
        fatal,
        `pageerrors on ${route.path}: ${fatal.map((f) => f.text).join('; ')}`,
      ).toEqual([])
    })
  }

  test('sidebar links navigate between pages', async ({ page }) => {
    await page.goto(FRONTEND_URL)
    await page.waitForLoadState('networkidle').catch(() => {})

    for (const target of ['/tasks', '/agents', '/search', '/settings']) {
      const link = page.locator(`a[href="${target}"]`).first()
      if (!(await link.isVisible().catch(() => false))) continue
      await link.click()
      await page.waitForURL(new RegExp(target.replace('/', '\\/')), {
        timeout: 10_000,
      })
      expect(page.url()).toContain(target)
    }
  })
})
