/**
 * Tests for useWebSocket hook.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'

// We need to import after mocking, so use dynamic import
describe('useWebSocket Hook', () => {
  let mockWs: any

  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()

    mockWs = {
      readyState: WebSocket.CONNECTING,
      onopen: null as (() => void) | null,
      onclose: null as (() => void) | null,
      onerror: null as ((e: any) => void) | null,
      onmessage: null as ((e: any) => void) | null,
      send: vi.fn(),
      close: vi.fn(function (this: any) {
        this.readyState = WebSocket.CLOSED
        if (this.onclose) this.onclose()
      }),
    }

    global.WebSocket = vi.fn(function (this: any, url: string) {
      this.readyState = WebSocket.CONNECTING
      this.onopen = null
      this.onclose = null
      this.onerror = null
      this.onmessage = null
      this.send = vi.fn()
      this.close = vi.fn(function (this: any) {
        this.readyState = WebSocket.CLOSED
        if (this.onclose) this.onclose()
      })
      mockWs = this
      // Auto-open on next tick
      setTimeout(() => {
        this.readyState = WebSocket.OPEN
        if (this.onopen) this.onopen()
      }, 0)
    }) as any
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  describe('basic usage', () => {
    it('should connect automatically when URL is provided', async () => {
      const { useWebSocket } = await import('../useWebSocket')
      const { result } = renderHook(() => useWebSocket('ws://localhost:8000/ws'))

      await act(async () => {
        await vi.advanceTimersByTimeAsync(10)
      })

      expect(result.current.connectionStatus).toBe('connected')
    })

    it('should be disconnected when URL is null', async () => {
      const { useWebSocket } = await import('../useWebSocket')
      const { result } = renderHook(() => useWebSocket(null))

      expect(result.current.connectionStatus).toBe('disconnected')
    })

    it('should send messages when connected', async () => {
      const { useWebSocket } = await import('../useWebSocket')
      const { result } = renderHook(() => useWebSocket('ws://localhost:8000/ws'))

      await act(async () => {
        await vi.advanceTimersByTimeAsync(10)
      })

      const sent = result.current.sendMessage({ type: 'test' })
      expect(sent).toBe(true)
      expect(mockWs.send).toHaveBeenCalledWith(JSON.stringify({ type: 'test' }))
    })

    it('should handle null URL gracefully', async () => {
      // Dynamic import to get fresh module reference
      const mod = await import('../useWebSocket?null-url-test')
      const { useWebSocket } = mod
      const { result } = renderHook(() => useWebSocket(null))

      expect(result.current.connectionStatus).toBe('disconnected')
    })
  })

  describe('connection lifecycle', () => {
    it('should set status to disconnected on close', async () => {
      const { useWebSocket } = await import('../useWebSocket')
      const { result } = renderHook(() => useWebSocket('ws://localhost:8000/ws'))

      await act(async () => {
        await vi.advanceTimersByTimeAsync(10)
      })

      expect(result.current.connectionStatus).toBe('connected')

      act(() => {
        result.current.disconnect()
      })

      expect(result.current.connectionStatus).toBe('disconnected')
    })

    it('should handle errors', async () => {
      global.WebSocket = vi.fn(function (this: any, url: string) {
        this.readyState = WebSocket.CONNECTING
        this.onopen = null
        this.onclose = null
        this.onerror = null
        this.onmessage = null
        this.send = vi.fn()
        this.close = vi.fn()
        mockWs = this
        setTimeout(() => {
          if (this.onerror) this.onerror(new Event('error'))
        }, 0)
      }) as any

      const { useWebSocket } = await import('../useWebSocket')
      const { result } = renderHook(() => useWebSocket('ws://localhost:8000/ws'))

      await act(async () => {
        await vi.advanceTimersByTimeAsync(10)
      })

      expect(result.current.connectionStatus).toBe('error')
    })
  })

  describe('message handling', () => {
    it('should receive messages', async () => {
      const { useWebSocket } = await import('../useWebSocket')
      const { result } = renderHook(() => useWebSocket('ws://localhost:8000/ws'))

      await act(async () => {
        await vi.advanceTimersByTimeAsync(10)
      })

      act(() => {
        if (mockWs.onmessage) {
          mockWs.onmessage({ data: JSON.stringify({ type: 'test', data: 'hello' }) })
        }
      })

      expect(result.current.lastMessage).toBeDefined()
      expect(JSON.parse(result.current.lastMessage.data)).toEqual({ type: 'test', data: 'hello' })
    })
  })

  describe('callbacks', () => {
    it('should call onOpen callback', async () => {
      const onOpen = vi.fn()
      const { useWebSocket } = await import('../useWebSocket')
      renderHook(() => useWebSocket('ws://localhost:8000/ws', { onOpen }))

      await act(async () => {
        await vi.advanceTimersByTimeAsync(10)
      })

      expect(onOpen).toHaveBeenCalled()
    })

    it('should call onError callback', async () => {
      const onError = vi.fn()
      global.WebSocket = vi.fn(function (this: any, url: string) {
        this.readyState = WebSocket.CONNECTING
        this.onopen = null
        this.onclose = null
        this.onerror = null
        this.onmessage = null
        this.send = vi.fn()
        this.close = vi.fn()
        mockWs = this
        setTimeout(() => {
          if (this.onerror) this.onerror(new Event('error'))
        }, 0)
      }) as any

      const { useWebSocket } = await import('../useWebSocket')
      renderHook(() => useWebSocket('ws://localhost:8000/ws', { onError }))

      await act(async () => {
        await vi.advanceTimersByTimeAsync(10)
      })

      expect(onError).toHaveBeenCalled()
    })

    it('should call onMessage callback', async () => {
      const onMessage = vi.fn()
      const { useWebSocket } = await import('../useWebSocket')
      renderHook(() => useWebSocket('ws://localhost:8000/ws', { onMessage }))

      await act(async () => {
        await vi.advanceTimersByTimeAsync(10)
      })

      const msgEvent = { data: JSON.stringify({ type: 'test' }) }
      act(() => {
        if (mockWs.onmessage) mockWs.onmessage(msgEvent)
      })

      expect(onMessage).toHaveBeenCalled()
    })
  })

  describe('cleanup', () => {
    it('should disconnect on unmount', async () => {
      const { useWebSocket } = await import('../useWebSocket')
      const { result, unmount } = renderHook(() => useWebSocket('ws://localhost:8000/ws'))

      await act(async () => {
        await vi.advanceTimersByTimeAsync(10)
      })

      unmount()

      expect(mockWs.close).toHaveBeenCalled()
    })
  })
})

describe('useGlobalWebSocket Hook', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()

    global.WebSocket = vi.fn(function (this: any, url: string) {
      this.readyState = WebSocket.OPEN
      this.onopen = null
      this.onclose = null
      this.onerror = null
      this.onmessage = null
      this.send = vi.fn()
      this.close = vi.fn()
    }) as any
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('should return connection state', async () => {
    const { useGlobalWebSocket } = await import('../useWebSocket')
    const { result } = renderHook(() => useGlobalWebSocket())

    expect(result.current).toBeDefined()
    expect(result.current.connectionStatus).toBeDefined()
    expect(result.current.sendMessage).toBeDefined()
  })
})
