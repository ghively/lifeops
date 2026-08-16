/**
 * Tests for useAgentNotifications hook.
 *
 * The hook polls agentsApi.list via react-query when enabled and fires a
 * Notification whenever an agent's status or current_task changes between
 * polls. It returns no public API - observable effects are the Notification
 * constructor / showNotification calls.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import { useAgentNotifications } from '../useAgentNotifications'
import { agentsApi } from '@/services/api'

vi.mock('@/services/api', () => ({
  agentsApi: {
    list: vi.fn(),
  },
}))

const mockList = agentsApi.list as unknown as ReturnType<typeof vi.fn>

function wrapper(client: QueryClient) {
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children)
}

function makeClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
    },
  })
}

describe('useAgentNotifications Hook', () => {
  let NotificationCtor: any

  let originalSW: any

  beforeEach(() => {
    vi.clearAllMocks()
    mockList.mockResolvedValue({ agents: [] })

    // Stub a Notification constructor with permission='granted'
    NotificationCtor = vi.fn()
    NotificationCtor.permission = 'granted'
    ;(globalThis as any).Notification = NotificationCtor

    // Stub navigator.serviceWorker.ready to resolve with a registration whose
    // showNotification proxies to our NotificationCtor spy. This keeps the
    // primary code path exercised deterministically.
    originalSW = Object.getOwnPropertyDescriptor(navigator, 'serviceWorker')
    const fakeRegistration = {
      showNotification: (title: string, options: NotificationOptions) => {
        NotificationCtor(title, options)
        return Promise.resolve()
      },
    }
    try {
      Object.defineProperty(navigator, 'serviceWorker', {
        value: { ready: Promise.resolve(fakeRegistration) },
        configurable: true,
      })
    } catch {
      // noop
    }
  })

  afterEach(() => {
    delete (globalThis as any).Notification
    if (originalSW) {
      try {
        Object.defineProperty(navigator, 'serviceWorker', originalSW)
      } catch {
        // noop
      }
    } else {
      try {
        // @ts-expect-error cleanup
        delete (navigator as any).serviceWorker
      } catch {
        // noop
      }
    }
  })

  it('does nothing when disabled', async () => {
    const client = makeClient()
    renderHook(() => useAgentNotifications(false), { wrapper: wrapper(client) })

    // Allow any pending microtasks
    await new Promise((r) => setTimeout(r, 10))

    expect(mockList).not.toHaveBeenCalled()
    expect(NotificationCtor).not.toHaveBeenCalled()
  })

  it('fetches agent list when enabled', async () => {
    const client = makeClient()
    renderHook(() => useAgentNotifications(true), { wrapper: wrapper(client) })

    await waitFor(() => {
      expect(mockList).toHaveBeenCalled()
    })
  })

  it('does not notify on initial load', async () => {
    mockList.mockResolvedValue({
      agents: [
        { id: 'a1', name: 'one', status: 'idle', current_task: null, current_action: null },
      ],
    })
    const client = makeClient()
    renderHook(() => useAgentNotifications(true), { wrapper: wrapper(client) })

    await waitFor(() => expect(mockList).toHaveBeenCalled())
    await new Promise((r) => setTimeout(r, 10))

    expect(NotificationCtor).not.toHaveBeenCalled()
  })

  it('fires a Notification when agent status changes between polls', async () => {
    mockList.mockResolvedValue({
      agents: [
        { id: 'a1', name: 'one', status: 'idle', current_task: null, current_action: null },
      ],
    })
    const client = makeClient()
    const { rerender } = renderHook(() => useAgentNotifications(true), {
      wrapper: wrapper(client),
    })

    await waitFor(() => expect(mockList).toHaveBeenCalled())
    // Allow the initial effect (which primes previousAgentsRef) to run.
    await new Promise((r) => setTimeout(r, 20))

    // Now update mock so the refetch returns a changed status.
    mockList.mockResolvedValue({
      agents: [
        { id: 'a1', name: 'one', status: 'active', current_task: null, current_action: null },
      ],
    })
    await client.refetchQueries({ queryKey: ['agent-notifications'] })
    rerender()

    await waitFor(() => {
      expect(NotificationCtor).toHaveBeenCalled()
    })
    const [title, options] = NotificationCtor.mock.calls[0]
    expect(title).toMatch(/@one/)
    expect(options).toMatchObject({ tag: 'agent-a1' })
  })

  it('does nothing when permission is not granted', async () => {
    NotificationCtor.permission = 'denied'
    mockList.mockResolvedValueOnce({
      agents: [
        { id: 'a1', name: 'one', status: 'idle', current_task: null, current_action: null },
      ],
    })
    const client = makeClient()
    const { rerender } = renderHook(() => useAgentNotifications(true), {
      wrapper: wrapper(client),
    })

    await waitFor(() => expect(mockList).toHaveBeenCalled())

    mockList.mockResolvedValueOnce({
      agents: [
        { id: 'a1', name: 'one', status: 'active', current_task: null, current_action: null },
      ],
    })
    await client.refetchQueries({ queryKey: ['agent-notifications'] })
    rerender()

    await new Promise((r) => setTimeout(r, 20))
    expect(NotificationCtor).not.toHaveBeenCalled()
  })

  it('does not notify when nothing changed between polls', async () => {
    const payload = {
      agents: [
        { id: 'a1', name: 'one', status: 'idle', current_task: null, current_action: null },
      ],
    }
    mockList.mockResolvedValue(payload)
    const client = makeClient()
    const { rerender } = renderHook(() => useAgentNotifications(true), {
      wrapper: wrapper(client),
    })

    await waitFor(() => expect(mockList).toHaveBeenCalled())

    await client.refetchQueries({ queryKey: ['agent-notifications'] })
    rerender()
    await new Promise((r) => setTimeout(r, 20))

    expect(NotificationCtor).not.toHaveBeenCalled()
  })

  it('notifies when current_task changes', async () => {
    mockList.mockResolvedValue({
      agents: [
        { id: 'a1', name: 'one', status: 'idle', current_task: null, current_action: null },
      ],
    })
    const client = makeClient()
    const { rerender } = renderHook(() => useAgentNotifications(true), {
      wrapper: wrapper(client),
    })

    await waitFor(() => expect(mockList).toHaveBeenCalled())
    await new Promise((r) => setTimeout(r, 20))

    mockList.mockResolvedValue({
      agents: [
        { id: 'a1', name: 'one', status: 'idle', current_task: 'Deploy app', current_action: null },
      ],
    })
    await client.refetchQueries({ queryKey: ['agent-notifications'] })
    rerender()

    await waitFor(() => expect(NotificationCtor).toHaveBeenCalled())
    const [, options] = NotificationCtor.mock.calls[0]
    expect(options.body).toContain('Deploy app')
  })

  it('unmounts without errors', async () => {
    const client = makeClient()
    const { unmount } = renderHook(() => useAgentNotifications(true), {
      wrapper: wrapper(client),
    })

    await waitFor(() => expect(mockList).toHaveBeenCalled())
    expect(() => unmount()).not.toThrow()
  })
})
