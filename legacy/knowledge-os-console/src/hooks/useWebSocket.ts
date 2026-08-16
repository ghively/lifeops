import { useEffect, useRef, useState, useCallback } from 'react'
import { getSystemWsUrl } from '@/lib/wsUrl'

export type WebSocketStatus = 'connecting' | 'connected' | 'disconnected' | 'error'

const GLOBAL_WS_URL = getSystemWsUrl()

interface UseWebSocketOptions {
  onOpen?: () => void
  onClose?: () => void
  onError?: (error: Event) => void
  onMessage?: (event: MessageEvent) => void
  reconnectAttempts?: number
  reconnectInterval?: number
}

export function useWebSocket(
  url: string | null,
  options: UseWebSocketOptions = {}
) {
  const {
    onOpen,
    onClose,
    onError,
    onMessage,
    reconnectAttempts = 5,
    reconnectInterval = 3000,
  } = options

  const [connectionStatus, setConnectionStatus] = useState<WebSocketStatus>('disconnected')
  const [lastMessage, setLastMessage] = useState<MessageEvent | null>(null)
  
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectCountRef = useRef(0)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const isManualCloseRef = useRef(false)

  const connect = useCallback(() => {
    if (!url) return

    // Close existing connection
    if (wsRef.current) {
      isManualCloseRef.current = true
      wsRef.current.close()
    }

    isManualCloseRef.current = false
    setConnectionStatus('connecting')

    try {
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        setConnectionStatus('connected')
        reconnectCountRef.current = 0
        onOpen?.()
      }

      ws.onclose = () => {
        setConnectionStatus('disconnected')
        onClose?.()

        // Attempt reconnection if not manually closed
        if (!isManualCloseRef.current && reconnectCountRef.current < reconnectAttempts) {
          reconnectCountRef.current += 1
          reconnectTimerRef.current = setTimeout(() => {
            connect()
          }, reconnectInterval)
        }
      }

      ws.onerror = (error) => {
        setConnectionStatus('error')
        onError?.(error)
      }

      ws.onmessage = (event) => {
        setLastMessage(event)
        onMessage?.(event)
      }
    } catch (error) {
      setConnectionStatus('error')
      console.error('WebSocket connection error:', error)
    }
  }, [url, onOpen, onClose, onError, onMessage, reconnectAttempts, reconnectInterval])

  const disconnect = useCallback(() => {
    isManualCloseRef.current = true
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    setConnectionStatus('disconnected')
  }, [])

  const sendMessage = useCallback((data: string | object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      const message = typeof data === 'string' ? data : JSON.stringify(data)
      wsRef.current.send(message)
      return true
    }
    return false
  }, [])

  // Connect when URL changes
  useEffect(() => {
    if (url) {
      connect()
    } else {
      disconnect()
    }

    return () => {
      disconnect()
    }
  }, [url, connect, disconnect])

  return {
    connectionStatus,
    lastMessage,
    sendMessage,
    connect,
    disconnect,
  }
}

// Hook for global WebSocket connection (for system-wide updates)
export function useGlobalWebSocket() {
  const { connectionStatus, lastMessage, sendMessage } = useWebSocket(GLOBAL_WS_URL)

  return {
    connectionStatus,
    lastMessage,
    sendMessage,
  }
}
