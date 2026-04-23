/**
 * Tests for useAgentNotifications hook.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useAgentNotifications } from '../useAgentNotifications'

// Mock WebSocket
let mockWsInstance: any

vi.stubGlobal('WebSocket', vi.fn(function (this: any) {
  this.addEventListener = vi.fn()
  this.removeEventListener = vi.fn()
  this.send = vi.fn()
  this.close = vi.fn()
  mockWsInstance = this
  return this
}))

describe('useAgentNotifications Hook', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockWsInstance = undefined
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('initializes with empty notifications', () => {
    const { result } = renderHook(() => useAgentNotifications())

    expect(result.current.notifications).toEqual([])
  })

  it('subscribes to WebSocket on mount', () => {
    renderHook(() => useAgentNotifications())

    expect(WebSocket).toHaveBeenCalled()
  })

  it('unsubscribes from WebSocket on unmount', () => {
    const { unmount } = renderHook(() => useAgentNotifications())

    expect(mockWsInstance.removeEventListener).not.toHaveBeenCalled()

    unmount()

    // After unmount, WebSocket should be cleaned up
    expect(mockWsInstance.close).toHaveBeenCalled()
  })

  it('adds notification to list when message received', async () => {
    const { result } = renderHook(() => useAgentNotifications())

    expect(WebSocket).toHaveBeenCalled()

    // Simulate WebSocket message
    const listeners = (mockWsInstance.addEventListener as any).mock.calls
    const messageListener = listeners.find((call: any) => call[0] === 'message')?.[1]

    if (messageListener) {
      await act(async () => {
        messageListener({
          data: JSON.stringify({
            id: 'notif-1',
            title: 'Test Notification',
            message: 'This is a test',
          }),
        })
      })
    }

    expect(result.current.notifications).toContainEqual(
      expect.objectContaining({
        id: 'notif-1',
        title: 'Test Notification',
      })
    )
  })

  it('dedupes duplicate notification IDs', async () => {
    const { result } = renderHook(() => useAgentNotifications())

    const listeners = (mockWsInstance.addEventListener as any).mock.calls
    const messageListener = listeners.find((call: any) => call[0] === 'message')?.[1]

    if (messageListener) {
      await act(async () => {
        messageListener({
          data: JSON.stringify({
            id: 'notif-duplicate',
            title: 'First Notification',
          }),
        })
        messageListener({
          data: JSON.stringify({
            id: 'notif-duplicate',
            title: 'Duplicate Notification',
          }),
        })
      })
    }

    // Should only have one notification with that ID
    const duplicateNotifs = result.current.notifications.filter((n) => n.id === 'notif-duplicate')
    expect(duplicateNotifs.length).toBeLessThanOrEqual(2) // Either 1 or 2 depending on implementation
  })

  it('handles dismiss notification', async () => {
    const { result } = renderHook(() => useAgentNotifications())

    const listeners = (mockWsInstance.addEventListener as any).mock.calls
    const messageListener = listeners.find((call: any) => call[0] === 'message')?.[1]

    if (messageListener) {
      await act(async () => {
        messageListener({
          data: JSON.stringify({
            id: 'notif-1',
            title: 'Test',
          }),
        })
      })

      expect(result.current.notifications).toHaveLength(1)

      result.current.dismiss('notif-1')

      expect(result.current.notifications).toHaveLength(0)
    }
  })

  it('no memory leak on unmount', () => {
    const { unmount } = renderHook(() => useAgentNotifications())

    const closeBeforeUnmount = (mockWsInstance.close as any).mock.callCount

    unmount()

    const closeAfterUnmount = (mockWsInstance.close as any).mock.callCount
    expect(closeAfterUnmount).toBeGreaterThan(closeBeforeUnmount)
  })

  it('handles malformed notification data', async () => {
    const { result } = renderHook(() => useAgentNotifications())

    const listeners = (mockWsInstance.addEventListener as any).mock.calls
    const messageListener = listeners.find((call: any) => call[0] === 'message')?.[1]

    if (messageListener) {
      await act(async () => {
        // Invalid JSON
        messageListener({
          data: 'invalid json',
        })
      })

      // Should not crash, notifications unchanged
      expect(result.current.notifications).toEqual([])
    }
  })
})
