/**
 * Auth state and the axios wiring that depends on it.
 *
 * The properties that matter: a stored token rides every request as a Bearer
 * header; a 401 from any endpoint except login drops the token and sends the
 * app to the login screen; a 401 from login itself is a wrong password and
 * must not tear down the session state.
 */

import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import {
  clearToken,
  getToken,
  handleUnauthorized,
  setToken,
  useAuthStore,
} from '@/lib/auth'
import { LifeOpsError, lifeops } from '@/services/lifeops'

const originalAdapter = lifeops.defaults.adapter

function adapterReturning(
  status: number,
  data: unknown,
  capture?: (config: InternalAxiosRequestConfig) => void,
): AxiosAdapter {
  return async (config) => {
    capture?.(config)
    const response: AxiosResponse = {
      data,
      status,
      statusText: '',
      headers: {},
      config,
    }
    // Default validateStatus rejects >= 300, which is what drives the error
    // interceptor exactly as a real response would.
    if (status >= 200 && status < 300) return response
    throw Object.assign(new Error(`status ${status}`), { response, config })
  }
}

beforeEach(() => {
  localStorage.clear()
  useAuthStore.setState({ status: 'unknown' })
})

afterEach(() => {
  lifeops.defaults.adapter = originalAdapter
  localStorage.clear()
})

describe('auth store', () => {
  it('persists the token and marks the session authenticated', () => {
    setToken('tok_123')
    expect(getToken()).toBe('tok_123')
    expect(useAuthStore.getState().status).toBe('authenticated')
  })

  it('clears the token and demands login on unauthorized', () => {
    setToken('tok_123')
    handleUnauthorized()
    expect(getToken()).toBeNull()
    expect(useAuthStore.getState().status).toBe('unauthenticated')
  })

  it('clearToken removes only storage, not the store', () => {
    setToken('tok_123')
    clearToken()
    expect(getToken()).toBeNull()
    expect(useAuthStore.getState().status).toBe('authenticated')
  })
})

describe('request interceptor', () => {
  it('attaches the stored token as a Bearer header', async () => {
    setToken('tok_abc')
    let seen: string | null = null
    lifeops.defaults.adapter = adapterReturning(200, {}, (config) => {
      seen = (config.headers.get('Authorization') as string | null) ?? null
    })
    await lifeops.get('/auth/me')
    expect(seen).toBe('Bearer tok_abc')
  })

  it('sends no Authorization header without a token', async () => {
    let seen: unknown = 'unset'
    lifeops.defaults.adapter = adapterReturning(200, {}, (config) => {
      seen = config.headers.get('Authorization') ?? null
    })
    await lifeops.get('/auth/me')
    expect(seen).toBeNull()
  })
})

describe('response interceptor', () => {
  it('drops the session on a 401 from an ordinary endpoint', async () => {
    setToken('tok_old')
    lifeops.defaults.adapter = adapterReturning(401, {
      code: 'auth_required',
      message: 'authentication required',
    })
    const failure = await lifeops.get('/tasks').catch((e: unknown) => e)
    expect(failure).toBeInstanceOf(LifeOpsError)
    expect((failure as LifeOpsError).code).toBe('auth_required')
    expect(getToken()).toBeNull()
    expect(useAuthStore.getState().status).toBe('unauthenticated')
  })

  it('treats a 401 from login as a wrong password, not a session teardown', async () => {
    setToken('tok_kept')
    lifeops.defaults.adapter = adapterReturning(401, {
      code: 'invalid_credentials',
      message: 'wrong password',
    })
    const failure = await lifeops
      .post('/auth/login', { password: 'nope' })
      .catch((e: unknown) => e)
    expect((failure as LifeOpsError).code).toBe('invalid_credentials')
    // The stored token and status are untouched; the login form shows the error.
    expect(getToken()).toBe('tok_kept')
    expect(useAuthStore.getState().status).toBe('authenticated')
  })
})
