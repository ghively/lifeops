import { test, expect } from '@playwright/test'
import { captureBrowserLogs } from '../../helpers/console'
import { FRONTEND_URL } from '../../helpers/env'

const PAGES = [
  '/',
  '/tasks',
  '/files',
  '/agents',
  '/search',
  '/settings',
  '/logs',
] as const

test.describe('Cross-cutting: no uncaught browser errors per page', () => {
  for (const path of PAGES) {
    test(`${path} is free of pageerrors and failed requests`, async ({ page }) => {
      const cap = captureBrowserLogs(page)
      await page.goto(`${FRONTEND_URL}${path}`, {
        waitUntil: 'domcontentloaded',
      })
      await page.waitForLoadState('networkidle').catch(() => {})
      // Give async effects 500ms to settle.
      await page.waitForTimeout(500)
      cap.detach()

      const fatal = cap.logs.filter((l) => l.type === 'pageerror')
      const failed = cap.logs.filter(
        (l) =>
          l.type === 'requestfailed' &&
          // Ignore expected dev-only HMR / Vite probes.
          !/\/@vite|\/__vite|hmr/i.test(l.url || ''),
      )

      expect(
        fatal,
        `pageerrors on ${path}: ${fatal.map((f) => f.text).join('; ')}`,
      ).toEqual([])
      expect(
        failed,
        `failed requests on ${path}: ${failed.map((f) => `${f.url} (${f.text})`).join('; ')}`,
      ).toEqual([])
    })
  }
})
