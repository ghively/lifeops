/**
 * Tests for WebSocket store.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useWebSocketStore } from '../websocket'

// Mock WebSocket
class MockWebSocket {
  static OPEN = 1
  static CLOSED = 3
  static CONNECTING = 0
  static CLOSING = 2

  readyState = MockWebSocket.CONNECTING
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onerror: ((error: unknown) => void) | null = null

  send = vi.fn()
  close = vi.fn(() => {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.()
  })

  constructor(public url: string) {
    // Simulate async open
    setTimeout(() => {
      this.readyState = MockWebSocket.OPEN
      this.onopen?.()
    }, 0)
  }
}

describe('WebSocket Store', () => {
  let originalWebSocket: typeof WebSocket

  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    originalWebSocket = global.WebSocket
    // Reset store state
    useWebSocketStore.setState({
      socket: null,
      isConnected: false,
      reconnectAttempts: 0,
      lastMessage: null,
    })
  })

  afterEach(() => {
    vi.useRealTimers()
    global.WebSocket = originalWebSocket
  })

  describe('initial state', () => {
    it('should have correct initial state', () => {
      const state = useWebSocketStore.getState()
      expect(state.socket).toBeNull()
      expect(state.isConnected).toBe(false)
      expect(state.reconnectAttempts).toBe(0)
      expect(state.lastMessage).toBeNull()
    })
  })

  describe('connect', () => {
    it('should create WebSocket connection', async () => {
      global.WebSocket = MockWebSocket as any
      useWebSocketStore.getState().connect()
      
      // Wait for async open
      await vi.advanceTimersByTimeAsync(10)
      
      const socket = useWebSocketStore.getState().socket
      expect(socket).not.toBeNull()
    })

    it('should set isConnected on open', async () => {
      global.WebSocket = MockWebSocket as any
      useWebSocketStore.getState().connect()
      
      // Wait for async open
      await vi.advanceTimersByTimeAsync(10)
      
      expect(useWebSocketStore.getState().isConnected).toBe(true)
    })

    it('should reset reconnect attempts on connect', async () => {
      global.WebSocket = MockWebSocket as any
      useWebSocketStore.setState({ reconnectAttempts: 3 })
      useWebSocketStore.getState().connect()
      
      await vi.advanceTimersByTimeAsync(10)
      
      expect(useWebSocketStore.getState().reconnectAttempts).toBe(0)
    })
  })

  describe('disconnect', () => {
    it('should close the connection', async () => {
      global.WebSocket = MockWebSocket as any
      useWebSocketStore.getState().connect()
      await vi.advanceTimersByTimeAsync(10)
      
      useWebSocketStore.getState().disconnect()
      
      expect(useWebSocketStore.getState().isConnected).toBe(false)
      expect(useWebSocketStore.getState().socket).toBeNull()
    })

    it('should handle disconnect when not connected', () => {
      useWebSocketStore.getState().disconnect()
      expect(useWebSocketStore.getState().socket).toBeNull()
    })
  })

  describe('send', () => {
    it('should send messages when connected', async () => {
      global.WebSocket = MockWebSocket as any
      useWebSocketStore.getState().connect()
      await vi.advanceTimersByTimeAsync(10)
      
      const mockSocket = useWebSocketStore.getState().socket as MockWebSocket
      useWebSocketStore.getState().send({ type: 'test', data: 'hello' })
      
      expect(mockSocket.send).toHaveBeenCalledWith(JSON.stringify({ type: 'test', data: 'hello' }))
    })

    it('should not send when not connected', () => {
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
      useWebSocketStore.getState().send({ type: 'test' })
      expect(consoleSpy).toHaveBeenCalledWith('WebSocket not connected')
      consoleSpy.mockRestore()
    })
  })

  describe('message handling', () => {
    it('should set lastMessage on message received', async () => {
      global.WebSocket = MockWebSocket as any
      useWebSocketStore.getState().connect()
      await vi.advanceTimersByTimeAsync(10)
      
      const mockSocket = useWebSocketStore.getState().socket as MockWebSocket
      mockSocket.onmessage!({ data: JSON.stringify({ type: 'test', data: 'hello' }) })
      
      expect(useWebSocketStore.getState().lastMessage).toEqual({ type: 'test', data: 'hello' })
    })
  })

  describe('reconnection', () => {
    it('should increment reconnect attempts on close', async () => {
      global.WebSocket = MockWebSocket as any
      useWebSocketStore.getState().connect()
      await vi.advanceTimersByTimeAsync(10)
      
      const mockSocket = useWebSocketStore.getState().socket as MockWebSocket
      mockSocket.onclose!()
      
      expect(useWebSocketStore.getState().reconnectAttempts).toBe(1)
    })
  })
})
