/**
 * Tests for useInstallPrompt hook.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useInstallPrompt } from '../useInstallPrompt'

describe('useInstallPrompt Hook', () => {
  let beforeInstallPromptEvent: any
  let originalMatchMedia: typeof window.matchMedia

  beforeEach(() => {
    vi.clearAllMocks()

    // Make sure matchMedia reports not-standalone so isInstalled is false.
    originalMatchMedia = window.matchMedia
    window.matchMedia = ((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })) as any

    // Build a minimal BeforeInstallPromptEvent-like object
    beforeInstallPromptEvent = new Event('beforeinstallprompt') as any
    beforeInstallPromptEvent.prompt = vi.fn().mockResolvedValue(undefined)
    beforeInstallPromptEvent.userChoice = Promise.resolve({ outcome: 'accepted', platform: '' })
  })

  afterEach(() => {
    window.matchMedia = originalMatchMedia
  })

  it('initializes with canInstall=false and isInstalled=false', () => {
    const { result } = renderHook(() => useInstallPrompt())

    expect(result.current.canInstall).toBe(false)
    expect(result.current.isInstalled).toBe(false)
  })

  it('captures beforeinstallprompt event and sets canInstall=true', async () => {
    const { result } = renderHook(() => useInstallPrompt())

    act(() => {
      window.dispatchEvent(beforeInstallPromptEvent)
    })

    await waitFor(() => {
      expect(result.current.canInstall).toBe(true)
    })
  })

  it('calls prompt() on stashed event when install() invoked', async () => {
    const { result } = renderHook(() => useInstallPrompt())

    act(() => {
      window.dispatchEvent(beforeInstallPromptEvent)
    })

    await waitFor(() => {
      expect(result.current.canInstall).toBe(true)
    })

    await act(async () => {
      await result.current.install()
    })

    expect(beforeInstallPromptEvent.prompt).toHaveBeenCalled()
  })

  it('clears canInstall after user accepts', async () => {
    const { result } = renderHook(() => useInstallPrompt())

    act(() => {
      window.dispatchEvent(beforeInstallPromptEvent)
    })

    await waitFor(() => {
      expect(result.current.canInstall).toBe(true)
    })

    await act(async () => {
      await result.current.install()
    })

    await waitFor(() => {
      expect(result.current.canInstall).toBe(false)
      expect(result.current.isInstalled).toBe(true)
    })
  })

  it('returns false from install() when user dismisses', async () => {
    beforeInstallPromptEvent.userChoice = Promise.resolve({ outcome: 'dismissed', platform: '' })

    const { result } = renderHook(() => useInstallPrompt())

    act(() => {
      window.dispatchEvent(beforeInstallPromptEvent)
    })

    await waitFor(() => {
      expect(result.current.canInstall).toBe(true)
    })

    let outcome: boolean | undefined
    await act(async () => {
      outcome = await result.current.install()
    })

    expect(outcome).toBe(false)
  })

  it('handles appinstalled event', async () => {
    const { result } = renderHook(() => useInstallPrompt())

    act(() => {
      window.dispatchEvent(beforeInstallPromptEvent)
    })

    await waitFor(() => {
      expect(result.current.canInstall).toBe(true)
    })

    act(() => {
      window.dispatchEvent(new Event('appinstalled'))
    })

    await waitFor(() => {
      expect(result.current.canInstall).toBe(false)
      expect(result.current.isInstalled).toBe(true)
    })
  })

  it('cleans up event listeners on unmount', () => {
    const removeSpy = vi.spyOn(window, 'removeEventListener')
    const { unmount } = renderHook(() => useInstallPrompt())

    unmount()

    expect(removeSpy).toHaveBeenCalledWith('beforeinstallprompt', expect.any(Function))
    expect(removeSpy).toHaveBeenCalledWith('appinstalled', expect.any(Function))

    removeSpy.mockRestore()
  })

  it('install() returns false when no prompt event is available', async () => {
    const { result } = renderHook(() => useInstallPrompt())

    expect(result.current.canInstall).toBe(false)

    let outcome: boolean | undefined
    await act(async () => {
      outcome = await result.current.install()
    })

    expect(outcome).toBe(false)
  })
})
