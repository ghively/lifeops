/**
 * Shared WebSocket URL utility — single source of truth for WS endpoint construction.
 * Used by useWebSocket hook, websocket store, and collaboration service.
 */

const DEFAULT_WS_PATH = '/ws/system'

function buildBaseUrl(): string {
  const configuredApiUrl = import.meta.env.VITE_API_URL as string | undefined
  if (configuredApiUrl) {
    return `${configuredApiUrl.replace(/^http/, 'ws')}`
  }

  if (typeof window !== 'undefined') {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${protocol}//${window.location.host}`
  }

  return ''
}

/** Get the system WebSocket URL (no auth token appended). */
export function getSystemWsUrl(): string {
  return `${buildBaseUrl()}${DEFAULT_WS_PATH}`
}

/**
 * Get a WebSocket URL for a given path, with optional auth token.
 * @param path - e.g. "/ws/system" or "/api/v1/collaboration/ws/{objectId}"
 * @param token - optional access token to append as query param
 */
export function getWsUrl(path: string, token?: string | null): string {
  const base = buildBaseUrl()
  const url = `${base}${path}`
  if (!token) return url
  const separator = url.includes('?') ? '&' : '?'
  return `${url}${separator}access_token=${encodeURIComponent(token)}`
}
