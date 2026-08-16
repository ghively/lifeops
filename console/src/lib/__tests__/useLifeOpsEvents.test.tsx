/**
 * Live-update wiring: server events invalidate the caches they touch, the
 * socket reconnects with backoff, and a server that refuses WebSockets
 * degrades to quiet polling.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'

import { setToken } from '@/lib/auth'
import { useLifeOpsEvents } from '@/lib/useLifeOpsEvents'

class FakeWebSocket {
  static instances: FakeWebSocket[] = []

  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  closed = false

  constructor(public readonly url: string) {
    FakeWebSocket.instances.push(this)
  }

  close() {
    this.closed = true
  }

  // test helpers
  open() {
    this.onopen?.()
  }
  emit(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) })
  }
  disconnect() {
    this.onclose?.()
  }
}

function setup() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  const view = renderHook(() => useLifeOpsEvents(), { wrapper })
  return { queryClient, invalidate, view }
}

beforeEach(() => {
  FakeWebSocket.instances = []
  localStorage.clear()
  vi.stubGlobal('WebSocket', FakeWebSocket)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('useLifeOpsEvents', () => {
  it('connects to /api/v1/events, carrying the token when one is stored', () => {
    setToken('tok_ws')
    setup()
    expect(FakeWebSocket.instances).toHaveLength(1)
    const url = new URL(FakeWebSocket.instances[0].url)
    expect(url.pathname).toBe('/api/v1/events')
    expect(url.searchParams.get('token')).toBe('tok_ws')
  })

  it('omits the token parameter when logged out (auth disabled)', () => {
    setup()
    const url = new URL(FakeWebSocket.instances[0].url)
    expect(url.searchParams.has('token')).toBe(false)
  })

  it('invalidates the task caches on task_changed', () => {
    const { invalidate } = setup()
    const socket = FakeWebSocket.instances[0]
    socket.open()
    socket.emit({ type: 'task_changed' })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['lifeops', 'tasks'] })
  })

  it('invalidates config caches on config_changed', () => {
    const { invalidate } = setup()
    const socket = FakeWebSocket.instances[0]
    socket.open()
    socket.emit({ type: 'config_changed' })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['lifeops', 'providers'] })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['lifeops', 'system-status'] })
  })

  it('falls back to a broad invalidation for unknown event types', () => {
    const { invalidate } = setup()
    const socket = FakeWebSocket.instances[0]
    socket.open()
    socket.emit({ type: 'something_new' })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['lifeops'] })
  })

  it('ignores malformed frames', () => {
    const { invalidate } = setup()
    const socket = FakeWebSocket.instances[0]
    socket.open()
    socket.onmessage?.({ data: 'not json at all' })
    expect(invalidate).not.toHaveBeenCalled()
  })

  it('reconnects with backoff after the socket closes', () => {
    vi.useFakeTimers()
    setup()
    expect(FakeWebSocket.instances).toHaveLength(1)
    FakeWebSocket.instances[0].open()
    FakeWebSocket.instances[0].disconnect()

    // attempts is now 1 → delay 2s
    vi.advanceTimersByTime(2_000)
    expect(FakeWebSocket.instances).toHaveLength(2)
  })

  it('degrades to polling after repeated connection failures', () => {
    vi.useFakeTimers()
    const { invalidate } = setup()
    // Burn through all five attempts without a successful open.
    for (let i = 0; i < 5; i += 1) {
      const socket = FakeWebSocket.instances[FakeWebSocket.instances.length - 1]
      socket.disconnect()
      vi.advanceTimersByTime(30_000)
    }
    expect(FakeWebSocket.instances).toHaveLength(5)

    invalidate.mockClear()
    vi.advanceTimersByTime(30_000)
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['lifeops'] })
    // No further socket attempts while polling.
    expect(FakeWebSocket.instances).toHaveLength(5)
  })

  it('closes the socket and stops timers on unmount', () => {
    const { view } = setup()
    const socket = FakeWebSocket.instances[0]
    view.unmount()
    expect(socket.closed).toBe(true)
  })
})
