import { test, expect } from '@playwright/test'
import { captureBrowserLogs } from '../../helpers/console'
import { BACKEND_URL, FRONTEND_URL } from '../../helpers/env'

// First-party hosts whose request failures count as app bugs. Anything else
// (Google Fonts CDN, analytics beacons, etc.) is environment-dependent —
// e.g. the e2e sandbox blocks outbound HTTPS to fonts.googleapis.com with
// ERR_CERT_AUTHORITY_INVALID, which is not a regression in the app.
const FIRST_PARTY_HOSTS = new Set(
  [FRONTEND_URL, BACKEND_URL].map((u) => new URL(u).host),
)
function isFirstParty(url: string | undefined): boolean {
  if (!url) return false
  try {
    return FIRST_PARTY_HOSTS.has(new URL(url).host)
  } catch {
    return false
  }
}

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
          !/\/@vite|\/__vite|hmr/i.test(l.url || '') &&
          // Only count failures against our own origins — third-party CDNs
          // (fonts, analytics) depend on the network sandbox, not the app.
          isFirstParty(l.url),
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
