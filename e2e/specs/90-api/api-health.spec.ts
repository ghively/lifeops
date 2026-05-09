import { test, expect } from '@playwright/test'
import { API_BASE, BACKEND_URL } from '../../helpers/env'
import { loginViaApi } from '../../helpers/auth'

// Smoke-checks the read-side of every router. We skip writes here because
// they create state we'd have to clean up, and the page specs already exercise
// happy-path writes through the UI.

const READ_ENDPOINTS = [
  { path: '/auth/me', auth: true },
  { path: '/objects', auth: true },
  { path: '/blocks', auth: true },
  { path: '/tasks', auth: true },
  { path: '/files', auth: true },
  { path: '/search?q=hello', auth: true },
  { path: '/agents', auth: true },
  { path: '/agents/runtime/sessions', auth: true },
  { path: '/system/status', auth: true },
  { path: '/relations', auth: true },
  { path: '/settings', auth: true },
  { path: '/webhooks', auth: true },
] as const

test.describe('API: read-side health', () => {
  test('backend /health is up', async ({ request }) => {
    const res = await request.get(`${BACKEND_URL}/health`, {
      failOnStatusCode: false,
    })
    expect(res.status()).toBe(200)
  })

  test('OpenAPI is exposed', async ({ request }) => {
    const res = await request.get(`${BACKEND_URL}/openapi.json`, {
      failOnStatusCode: false,
    })
    expect([200, 401]).toContain(res.status())
  })

  for (const ep of READ_ENDPOINTS) {
    test(`GET ${ep.path} responds (auth=${ep.auth})`, async ({ request }) => {
      const headers: Record<string, string> = {}
      if (ep.auth) {
        const token = await loginViaApi()
        if (!token) test.skip(true, 'could not obtain auth token')
        headers['Authorization'] = `Bearer ${token}`
      }
      const res = await request.get(`${API_BASE}${ep.path}`, {
        headers,
        failOnStatusCode: false,
      })
      // Accept any non-5xx response. 404 means feature not present yet, which
      // is real-but-not-fatal information for the report.
      expect(res.status()).toBeLessThan(500)
    })
  }

  test('unauthenticated read of protected endpoint returns 401', async ({
    request,
  }) => {
    const res = await request.get(`${API_BASE}/objects`, {
      failOnStatusCode: false,
    })
    expect([401, 403]).toContain(res.status())
  })

  test('agent_id path-traversal is rejected (regression for the audit fix)', async ({
    request,
  }) => {
    const token = await loginViaApi()
    if (!token) test.skip(true, 'could not obtain auth token')
    const res = await request.get(
      `${API_BASE}/agents/runtime/${encodeURIComponent('../escape')}/files/AGENT.md`,
      {
        headers: { Authorization: `Bearer ${token}` },
        failOnStatusCode: false,
      },
    )
    // Should be a clean 400, not 500 and not 200.
    expect([400, 404, 422]).toContain(res.status())
  })
})
