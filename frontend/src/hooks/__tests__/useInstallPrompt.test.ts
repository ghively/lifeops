/**
 * Tests for useInstallPrompt hook.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useInstallPrompt } from '../useInstallPrompt'

describe('useInstallPrompt Hook', () => {
  let beforeInstallPromptEvent: any

  beforeEach(() => {
    vi.clearAllMocks()

    // Create mock event
    beforeInstallPromptEvent = {
      prompt: vi.fn(),
      userChoice: Promise.resolve({ outcome: 'accepted' }),
    }

    // Reset event listeners
    const listeners: Record<string, Function[]> = {}

    global.addEventListener = vi.fn((event: string, listener: any) => {
      if (!listeners[event]) {
        listeners[event] = []
      }
      listeners[event].push(listener)
    })

    global.removeEventListener = vi.fn((event: string, listener: any) => {
      if (listeners[event]) {
        listeners[event] = listeners[event].filter((l) => l !== listener)
      }
    })

    // Store dispatch capability
    ;(global as any).__dispatchBeforeInstallPrompt = () => {
      if (listeners['beforeinstallprompt']) {
        listeners['beforeinstallprompt'].forEach((listener) => {
          listener(beforeInstallPromptEvent)
        })
      }
    }
  })

  it('initializes with null deferredPrompt', () => {
    const { result } = renderHook(() => useInstallPrompt())

    expect(result.current.deferredPrompt).toBeNull()
    expect(result.current.canInstall).toBe(false)
  })

  it('captures beforeinstallprompt event', async () => {
    const { result } = renderHook(() => useInstallPrompt())

    act(() => {
      ;(global as any).__dispatchBeforeInstallPrompt()
    })

    await waitFor(() => {
      expect(result.current.deferredPrompt).toBe(beforeInstallPromptEvent)
      expect(result.current.canInstall).toBe(true)
    })
  })

  it('calls prompt() on stashed event when promptInstall() invoked', async () => {
    const { result } = renderHook(() => useInstallPrompt())

    act(() => {
      ;(global as any).__dispatchBeforeInstallPrompt()
    })

    await waitFor(() => {
      expect(result.current.canInstall).toBe(true)
    })

    act(() => {
      result.current.promptInstall()
    })

    expect(beforeInstallPromptEvent.prompt).toHaveBeenCalled()
  })

  it('clears state after user choice', async () => {
    const { result } = renderHook(() => useInstallPrompt())

    act(() => {
      ;(global as any).__dispatchBeforeInstallPrompt()
    })

    await waitFor(() => {
      expect(result.current.canInstall).toBe(true)
    })

    act(() => {
      result.current.promptInstall()
    })

    // Wait for user choice
    await waitFor(() => {
      expect(beforeInstallPromptEvent.prompt).toHaveBeenCalled()
    })

    // After user choice, deferredPrompt should be cleared
    await waitFor(() => {
      expect(result.current.deferredPrompt).toBeNull()
    })
  })

  it('handles appinstalled event', async () => {
    const { result } = renderHook(() => useInstallPrompt())

    // Dispatch beforeinstallprompt
    act(() => {
      ;(global as any).__dispatchBeforeInstallPrompt()
    })

    await waitFor(() => {
      expect(result.current.canInstall).toBe(true)
    })

    // Simulate app installed event
    act(() => {
      const event = new Event('appinstalled')
      window.dispatchEvent(event)
    })

    // canInstall should become false after installation
    await waitFor(() => {
      expect(result.current.canInstall).toBe(false)
    })
  })

  it('cleans up event listeners on unmount', () => {
    const { unmount } = renderHook(() => useInstallPrompt())

    unmount()

    // removeEventListener should have been called
    expect(global.removeEventListener).toHaveBeenCalledWith(
      'beforeinstallprompt',
      expect.any(Function)
    )
  })

  it('handles promptInstall when deferredPrompt is null', () => {
    const { result } = renderHook(() => useInstallPrompt())

    expect(result.current.deferredPrompt).toBeNull()

    // Should not throw
    act(() => {
      result.current.promptInstall()
    })

    expect(result.current.canInstall).toBe(false)
  })

  it('subscription pattern works correctly', async () => {
    const { result: result1 } = renderHook(() => useInstallPrompt())
    const { result: result2 } = renderHook(() => useInstallPrompt())

    act(() => {
      ;(global as any).__dispatchBeforeInstallPrompt()
    })

    await waitFor(() => {
      expect(result1.current.canInstall).toBe(true)
      expect(result2.current.canInstall).toBe(true)
    })
  })
})
