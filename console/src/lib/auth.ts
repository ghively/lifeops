/**
 * Console authentication state (BUILD_SPEC section 90, SECURITY.md).
 *
 * Phase 1 adds a single-password login to LifeOps Core. The Console keeps the
 * returned bearer token in localStorage and attaches it to every request (see
 * the interceptors in `services/lifeops.ts`).
 *
 * Auth may be disabled server-side (local single-user installs). In that mode
 * `GET /auth/me` succeeds without a token and no 401 is ever emitted, so the
 * login screen must never appear. The Console discovers which mode it is in by
 * calling `me()` at bootstrap rather than by trusting a build-time flag.
 */

import { create } from 'zustand'

const TOKEN_KEY = 'lifeops_auth_token'

export type AuthStatus =
  /** Bootstrap has not answered yet — render nothing interactive. */
  | 'unknown'
  /** A token works, or the server has auth disabled. */
  | 'authenticated'
  /** The server demands a login. */
  | 'unauthenticated'

interface AuthState {
  status: AuthStatus
  setAuthenticated: () => void
  setUnauthenticated: () => void
}

export const useAuthStore = create<AuthState>()((set) => ({
  status: 'unknown',
  setAuthenticated: () => set({ status: 'authenticated' }),
  setUnauthenticated: () => set({ status: 'unauthenticated' }),
}))

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

/** Persist a freshly issued token and mark the session authenticated. */
export function setToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, token)
  } catch {
    // Storage unavailable (private mode, quota) — the session still works
    // until the tab closes; the next visit simply asks for the password again.
  }
  useAuthStore.getState().setAuthenticated()
}

export function clearToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY)
  } catch {
    // ignore
  }
}

/**
 * The server rejected our credentials. Drop the stored token so the next
 * attempt does not replay it, and send the app to the login screen.
 */
export function handleUnauthorized(): void {
  clearToken()
  useAuthStore.getState().setUnauthenticated()
}
