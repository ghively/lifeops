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

const MAX_RECONNECT_ATTEMPTS = 5
const RECONNECT_DELAY = 3000

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
      set({ 
        socket: ws, 
        isConnected: true,
        reconnectAttempts: 0 
      })
      
      // Send ping to keep connection alive
      const pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }))
        } else {
          clearInterval(pingInterval)
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
      set({ 
        socket: null, 
        isConnected: false,
        reconnectAttempts: reconnectAttempts + 1
      })
      
      // Attempt reconnect
      setTimeout(() => {
        get().connect()
      }, RECONNECT_DELAY)
    }

    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
    }
  },

  disconnect: () => {
    const { socket } = get()
    if (socket) {
      socket.close()
      set({ socket: null, isConnected: false })
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
