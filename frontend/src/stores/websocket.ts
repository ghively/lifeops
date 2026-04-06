import { create } from 'zustand'

const DEFAULT_WS_URL = (() => {
  const configuredApiUrl = import.meta.env.VITE_API_URL as string | undefined
  if (configuredApiUrl) {
    return `${configuredApiUrl.replace(/^http/, 'ws')}/ws/system`
  }

  if (typeof window !== 'undefined') {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${protocol}//${window.location.host}/ws/system`
  }

  return '/ws/system'
})()

function getAuthenticatedWsUrl() {
  const token = localStorage.getItem('access_token')
  if (!token) {
    return DEFAULT_WS_URL
  }
  const separator = DEFAULT_WS_URL.includes('?') ? '&' : '?'
  return `${DEFAULT_WS_URL}${separator}access_token=${encodeURIComponent(token)}`
}

interface WebSocketState {
  socket: WebSocket | null
  isConnected: boolean
  reconnectAttempts: number
  connect: () => void
  disconnect: () => void
  send: (message: unknown) => void
  lastMessage: unknown | null
}

const MAX_RECONNECT_ATTEMPTS = 10
const BASE_RECONNECT_DELAY = 3000
const MAX_RECONNECT_DELAY = 30000

// Module-level refs for timer IDs (not part of zustand state to avoid re-renders)
let pingIntervalId: ReturnType<typeof setInterval> | null = null
let reconnectTimerId: ReturnType<typeof setTimeout> | null = null

export const useWebSocketStore = create<WebSocketState>((set, get) => ({
  socket: null,
  isConnected: false,
  reconnectAttempts: 0,
  lastMessage: null,

  connect: () => {
    const { socket, reconnectAttempts } = get()
    
    if (socket?.readyState === WebSocket.OPEN) return
    if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      console.error('Max reconnect attempts reached')
      return
    }

    const ws = new WebSocket(getAuthenticatedWsUrl())

    ws.onopen = () => {
      console.log('WebSocket connected')

      // Clear any previous ping interval
      if (pingIntervalId !== null) {
        clearInterval(pingIntervalId)
        pingIntervalId = null
      }

      set({ 
        socket: ws, 
        isConnected: true,
        reconnectAttempts: 0 
      })
      
      // Send ping to keep connection alive
      pingIntervalId = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }))
        } else {
          if (pingIntervalId !== null) {
            clearInterval(pingIntervalId)
            pingIntervalId = null
          }
        }
      }, 30000)
    }

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data)
        set({ lastMessage: message })
        
        // Handle different message types
        console.log('WebSocket message:', message)
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e)
      }
    }

    ws.onclose = () => {
      console.log('WebSocket disconnected')

      // Clear ping interval on close
      if (pingIntervalId !== null) {
        clearInterval(pingIntervalId)
        pingIntervalId = null
      }

      const nextAttempts = reconnectAttempts + 1
      set({ 
        socket: null, 
        isConnected: false,
        reconnectAttempts: nextAttempts
      })
      
      // Attempt reconnect with exponential backoff
      const delay = Math.min(BASE_RECONNECT_DELAY * Math.pow(2, nextAttempts - 1), MAX_RECONNECT_DELAY)
      reconnectTimerId = setTimeout(() => {
        get().connect()
      }, delay)
    }

    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
    }
  },

  disconnect: () => {
    // Clear reconnect timer to prevent auto-reconnect after intentional disconnect
    if (reconnectTimerId !== null) {
      clearTimeout(reconnectTimerId)
      reconnectTimerId = null
    }

    // Clear ping interval
    if (pingIntervalId !== null) {
      clearInterval(pingIntervalId)
      pingIntervalId = null
    }

    const { socket } = get()
    if (socket) {
      socket.close()
      set({ socket: null, isConnected: false, reconnectAttempts: 0 })
    }
  },

  send: (message) => {
    const { socket } = get()
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(message))
    } else {
      console.warn('WebSocket not connected')
    }
  },
}))
