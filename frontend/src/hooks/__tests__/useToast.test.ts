/**
 * Tests for useToast hook.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useToast, toast } from '../useToast'

describe('useToast Hook', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('initializes with empty toasts', () => {
    const { result } = renderHook(() => useToast())

    expect(result.current.toasts).toEqual([])
  })

  it('adds toast to list when toast() is called', () => {
    const { result } = renderHook(() => useToast())

    act(() => {
      result.current.toast({
        title: 'Test Toast',
        description: 'Test message',
      })
    })

    expect(result.current.toasts).toHaveLength(1)
    expect(result.current.toasts[0]).toMatchObject({
      title: 'Test Toast',
      description: 'Test message',
    })
  })

  it('auto-dismisses toast after default duration', () => {
    const { result } = renderHook(() => useToast())

    act(() => {
      result.current.toast({ title: 'Auto-dismiss' })
    })

    expect(result.current.toasts).toHaveLength(1)

    act(() => {
      vi.advanceTimersByTime(4000)
    })

    expect(result.current.toasts).toHaveLength(0)
  })

  it('accumulates multiple toasts', () => {
    const { result } = renderHook(() => useToast())

    act(() => {
      for (let i = 0; i < 5; i++) {
        result.current.toast({ title: `Toast ${i}` })
      }
    })

    expect(result.current.toasts.length).toBe(5)
  })

  it('dismisses toast by ID', () => {
    const { result } = renderHook(() => useToast())

    let toastId: string | undefined

    act(() => {
      toastId = result.current.toast({ title: 'Dismissible Toast' })
    })

    expect(result.current.toasts).toHaveLength(1)

    act(() => {
      result.current.dismiss(toastId!)
    })

    expect(result.current.toasts).toHaveLength(0)
  })

  it('removes correct toast when dismissing by ID', () => {
    const { result } = renderHook(() => useToast())

    let toastId1: string | undefined
    let toastId2: string | undefined
    let toastId3: string | undefined

    act(() => {
      toastId1 = result.current.toast({ title: 'Toast 1' })
      toastId2 = result.current.toast({ title: 'Toast 2' })
      toastId3 = result.current.toast({ title: 'Toast 3' })
    })

    expect(result.current.toasts).toHaveLength(3)

    act(() => {
      result.current.dismiss(toastId2!)
    })

    expect(result.current.toasts).toHaveLength(2)
    expect(result.current.toasts.every((t) => t.id !== toastId2)).toBe(true)
    expect(result.current.toasts.some((t) => t.id === toastId1)).toBe(true)
    expect(result.current.toasts.some((t) => t.id === toastId3)).toBe(true)
  })

  it('generates unique IDs for each toast', () => {
    const { result } = renderHook(() => useToast())

    const ids = new Set<string | undefined>()

    act(() => {
      for (let i = 0; i < 5; i++) {
        const id = result.current.toast({ title: `Toast ${i}` })
        ids.add(id)
      }
    })

    expect(ids.size).toBe(5)
  })

  it('exported toast() notifies subscribed hooks', () => {
    const { result } = renderHook(() => useToast())

    act(() => {
      toast({ title: 'From singleton' })
    })

    expect(result.current.toasts.length).toBe(1)
    expect(result.current.toasts[0].title).toBe('From singleton')
  })

  it('supports destructive variant', () => {
    const { result } = renderHook(() => useToast())

    act(() => {
      result.current.toast({ title: 'Error', variant: 'destructive' })
    })

    expect(result.current.toasts[0].variant).toBe('destructive')
  })
})
