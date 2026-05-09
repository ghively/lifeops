import { request as pwRequest } from '@playwright/test'
import { API_BASE, TEST_USER } from './env'

/**
 * Idempotently ensure the test user exists. Returns true if the call succeeded
 * (user created OR already existed); false if the backend wasn't reachable.
 */
export async function ensureTestUser(): Promise<boolean> {
  const ctx = await pwRequest.newContext()
  try {
    const res = await ctx.post(`${API_BASE}/auth/register`, {
      data: {
        email: TEST_USER.email,
        username: TEST_USER.username,
        password: TEST_USER.password,
        full_name: TEST_USER.full_name,
      },
      failOnStatusCode: false,
    })
    // 200/201 = created; 400/409 = already exists; we accept anything that's
    // not a server error.
    return res.status() < 500
  } catch {
    return false
  } finally {
    await ctx.dispose()
  }
}

/**
 * Authenticate via the API and return the access token. Used by specs that
 * need to call the backend directly (not through the storage state).
 */
export async function loginViaApi(): Promise<string | null> {
  const ctx = await pwRequest.newContext()
  try {
    const res = await ctx.post(`${API_BASE}/auth/login`, {
      data: { email: TEST_USER.email, password: TEST_USER.password },
      failOnStatusCode: false,
    })
    if (!res.ok()) return null
    const body = await res.json()
    return body.access_token || body.accessToken || null
  } catch {
    return null
  } finally {
    await ctx.dispose()
  }
}
