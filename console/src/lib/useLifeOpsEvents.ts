/**
 * Live updates from LifeOps Core (BUILD_SPEC section 4: the Console has a
 * WebSocket/event stream).
 *
 * Mounts once in the shell. While the socket is open, every server event
 * invalidates the react-query caches that event touches, so open pages
 * refresh themselves. Reconnects with exponential backoff; if the server
 * keeps refusing the socket (older Core, proxy without upgrade support) it
 * degrades silently to slow polling of the whole `lifeops` cache namespace.
 */

import { useEffect } from 'react'
import { useQueryClient, type QueryClient } from '@tanstack/react-query'

import { getToken } from '@/lib/auth'
import { WS_BASE_URL } from '@/services/lifeops'

/** Event types the server may send on /api/v1/events. */
export type LifeOpsEventType =
  | 'task_changed'
  | 'preference_changed'
  | 'person_changed'
  | 'config_changed'

const MAX_BACKOFF_MS = 30_000
/** Consecutive connection failures before giving up on the socket. */
const MAX_WS_ATTEMPTS = 5
const POLL_INTERVAL_MS = 30_000

function eventsUrl(): string {
  const url = new URL(`${WS_BASE_URL}/api/v1/events`)
  // WebSocket requests cannot carry an Authorization header from the
  // browser, so the bearer token rides as a query parameter. Loopback-only
  // and never logged (the logger redacts token-bearing fields).
  const token = getToken()
  if (token) {
    url.searchParams.set('token', token)
  }
  return url.toString()
}

function invalidateFor(queryClient: QueryClient, type: string): void {
  switch (type) {
    case 'task_changed':
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'tasks'] })
      break
    case 'preference_changed':
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'preferences'] })
      break
    case 'person_changed':
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'me'] })
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'people'] })
      break
    case 'config_changed':
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'providers'] })
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'system-status'] })
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'system-config'] })
      break
    default:
      // Unknown event — cheaper to refresh everything than to miss one.
      void queryClient.invalidateQueries({ queryKey: ['lifeops'] })
  }
}

export function useLifeOpsEvents(): void {
  const queryClient = useQueryClient()

  useEffect(() => {
    if (typeof WebSocket === 'undefined') {
      return
    }

    let socket: WebSocket | null = null
    let attempts = 0
    let stopped = false
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let pollTimer: ReturnType<typeof setInterval> | null = null

    const stopPolling = () => {
      if (pollTimer !== null) {
        clearInterval(pollTimer)
        pollTimer = null
      }
    }

    const startPolling = () => {
      stopPolling()
      pollTimer = setInterval(() => {
        void queryClient.invalidateQueries({ queryKey: ['lifeops'] })
      }, POLL_INTERVAL_MS)
    }

    const connect = () => {
      if (stopped) return
      try {
        socket = new WebSocket(eventsUrl())
      } catch {
        attempts += 1
        scheduleReconnect()
        return
      }

      socket.onopen = () => {
        attempts = 0
        stopPolling()
      }

      socket.onmessage = (message: MessageEvent<string>) => {
        try {
          const event = JSON.parse(message.data) as { type?: string }
          if (event.type) {
            invalidateFor(queryClient, event.type)
          }
        } catch {
          // A malformed frame says nothing about our caches — ignore it.
        }
      }

      socket.onclose = () => {
        socket = null
        if (!stopped) {
          attempts += 1
          scheduleReconnect()
        }
      }

      socket.onerror = () => {
        // onclose follows and drives the reconnect; nothing to do here.
      }
    }

    const scheduleReconnect = () => {
      if (stopped || reconnectTimer !== null) return
      if (attempts >= MAX_WS_ATTEMPTS) {
        // The socket is not coming up — poll instead, quietly.
        startPolling()
        return
      }
      const delay = Math.min(1_000 * 2 ** attempts, MAX_BACKOFF_MS)
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null
        connect()
      }, delay)
    }

    connect()

    return () => {
      stopped = true
      if (reconnectTimer !== null) clearTimeout(reconnectTimer)
      stopPolling()
      if (socket) {
        socket.onclose = null
        socket.close()
      }
    }
  }, [queryClient])
}
