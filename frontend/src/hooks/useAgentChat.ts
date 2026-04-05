import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { agentRuntimeApi, APIError, type AgentChatRequest, type RuntimeChatEvent, type RuntimeAgentMessage } from '@/services/api'

export interface AgentChatUIMessage {
  id: string
  role: 'user' | 'assistant' | 'tool' | 'thinking' | 'error' | 'subagent'
  content: string
  createdAt: string
  toolName?: string
  status?: 'streaming' | 'complete'
  metadata?: Record<string, unknown>
}

interface UseAgentChatOptions {
  agentId?: string
  sessionId?: string | null
  initialMessages?: RuntimeAgentMessage[]
}

function mapHistoryMessage(message: RuntimeAgentMessage, index: number): AgentChatUIMessage {
  return {
    id: message.id || `history-${index}`,
    role: message.role === 'assistant' ? 'assistant' : message.role === 'tool' ? 'tool' : message.role === 'user' ? 'user' : 'thinking',
    content: message.content,
    createdAt: message.created_at || new Date().toISOString(),
    status: 'complete',
    metadata: message.metadata,
  }
}

function createMessageId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

export function useAgentChat({ agentId, sessionId, initialMessages = [] }: UseAgentChatOptions) {
  const [messages, setMessages] = useState<AgentChatUIMessage[]>(() => initialMessages.map(mapHistoryMessage))
  const [isStreaming, setIsStreaming] = useState(false)
  const [currentToolCall, setCurrentToolCall] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [activeSessionId, setActiveSessionId] = useState<string | null>(sessionId || null)
  const abortControllerRef = useRef<AbortController | null>(null)

  useEffect(() => {
    setMessages(initialMessages.map(mapHistoryMessage))
  }, [initialMessages])

  useEffect(() => {
    setActiveSessionId(sessionId || null)
  }, [sessionId])

  useEffect(() => () => abortControllerRef.current?.abort(), [])

  const sendMessage = useCallback(async (message: string) => {
    if (!agentId || !message.trim() || isStreaming) {
      return null
    }

    abortControllerRef.current?.abort()
    const abortController = new AbortController()
    abortControllerRef.current = abortController

    const sentAt = new Date().toISOString()
    const userMessageId = createMessageId('user')
    const assistantMessageId = createMessageId('assistant')

    setError(null)
    setIsStreaming(true)
    setCurrentToolCall(null)
    setMessages((current) => [
      ...current,
      { id: userMessageId, role: 'user', content: message, createdAt: sentAt, status: 'complete' },
      { id: assistantMessageId, role: 'assistant', content: '', createdAt: sentAt, status: 'streaming' },
    ])

    const body: AgentChatRequest = {
      agent_id: agentId,
      message,
      session_id: activeSessionId,
    }

    try {
      const { response } = await agentRuntimeApi.chatWithAgent(body)
      const reader = response.body?.getReader()

      if (!reader) {
        throw new APIError('Streaming response body was unavailable')
      }

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { value, done } = await reader.read()
        if (done) {
          break
        }

        if (abortController.signal.aborted) {
          break
        }

        buffer += decoder.decode(value, { stream: true })
        const chunks = buffer.split('\n\n')
        buffer = chunks.pop() || ''

        for (const chunk of chunks) {
          const parsed = parseSseChunk(chunk)
          if (!parsed) {
            continue
          }

          const event = parsed.data
          if (event.session_id) {
            setActiveSessionId(event.session_id)
          }

          if (event.type === 'text_delta' && event.delta) {
            setMessages((current) =>
              current.map((item) =>
                item.id === assistantMessageId
                  ? { ...item, content: `${item.content}${event.delta}` }
                  : item
              )
            )
          }

          if (event.type === 'thinking') {
            setMessages((current) => {
              const existing = current.find((item) => item.id === 'thinking-indicator')
              if (existing) {
                return current
              }

              return [
                ...current,
                {
                  id: 'thinking-indicator',
                  role: 'thinking',
                  content: 'Thinking...',
                  createdAt: new Date().toISOString(),
                  status: 'streaming',
                  metadata: event.data,
                },
              ]
            })
          }

          if (event.type === 'tool_start') {
            setCurrentToolCall(event.tool_name || 'tool')
            setMessages((current) => {
              const toolMessage: AgentChatUIMessage = {
                id: createMessageId('tool'),
                role: 'tool',
                content: event.tool_name ? `Running ${event.tool_name}` : 'Running tool',
                createdAt: new Date().toISOString(),
                toolName: event.tool_name,
                status: 'streaming',
                metadata: event.data,
              }

              return [...current.filter((item) => item.id !== 'thinking-indicator'), toolMessage]
            })
          }

          if (event.type === 'tool_result') {
            setCurrentToolCall(null)
            setMessages((current) => {
              const next = [...current]
              const index = next.findIndex((item) => item.role === 'tool' && item.status === 'streaming')
              const content = typeof event.data?.content === 'string'
                ? event.data.content
                : typeof event.message === 'string'
                  ? event.message
                  : `${event.tool_name || 'Tool'} finished`
              const toolMessage: AgentChatUIMessage = {
                id: createMessageId('tool'),
                role: 'tool',
                content,
                createdAt: new Date().toISOString(),
                toolName: event.tool_name,
                status: 'complete',
                metadata: event.data,
              }

              if (index >= 0) {
                next[index] = {
                  ...next[index],
                  content,
                  status: 'complete',
                  metadata: event.data,
                }
              } else {
                next.push(toolMessage)
              }

              return next
            })
          }

          if (event.type === 'error') {
            const messageText = event.message || 'Agent chat failed'
            setError(messageText)
            setMessages((current) => [
              ...current.filter((item) => item.id !== 'thinking-indicator'),
              {
                id: createMessageId('error'),
                role: 'error',
                content: messageText,
                createdAt: new Date().toISOString(),
                status: 'complete',
              },
            ])
          }

          if (event.type === 'subagent_start') {
            setMessages((current) => [
              ...current.filter((item) => item.id !== 'thinking-indicator'),
              {
                id: createMessageId('subagent'),
                role: 'subagent',
                content: `Delegating to ${(event.data?.agent_id as string) || 'sub-agent'}`,
                createdAt: new Date().toISOString(),
                status: 'streaming',
                metadata: event.data,
              },
            ])
          }

          if (event.type === 'subagent_result') {
            setMessages((current) => [
              ...current,
              {
                id: createMessageId('subagent'),
                role: 'subagent',
                content: typeof event.data?.content === 'string'
                  ? event.data.content
                  : typeof event.data?.error === 'string'
                    ? event.data.error
                    : `Sub-agent ${(event.data?.agent_id as string) || ''} finished`,
                createdAt: new Date().toISOString(),
                status: 'complete',
                metadata: event.data,
              },
            ])
          }

          if (event.type === 'done') {
            setCurrentToolCall(null)
            setMessages((current) =>
              current
                .filter((item) => item.id !== 'thinking-indicator')
                .map((item) =>
                  item.id === assistantMessageId
                    ? {
                        ...item,
                        content: item.content || event.message || '',
                        status: 'complete',
                      }
                    : item
                )
            )
          }
        }
      }

      return activeSessionId
    } catch (caughtError) {
      if (abortController.signal.aborted) {
        return null
      }

      const messageText = caughtError instanceof Error ? caughtError.message : 'Agent chat failed'
      setError(messageText)
      setMessages((current) => [
        ...current,
        {
          id: createMessageId('error'),
          role: 'error',
          content: messageText,
          createdAt: new Date().toISOString(),
          status: 'complete',
        },
      ])
      return null
    } finally {
      setIsStreaming(false)
      setCurrentToolCall(null)
      abortControllerRef.current = null
    }
  }, [activeSessionId, agentId, isStreaming])

  const resetMessages = useCallback((nextMessages: RuntimeAgentMessage[]) => {
    setMessages(nextMessages.map(mapHistoryMessage))
    setError(null)
    setCurrentToolCall(null)
    setIsStreaming(false)
  }, [])

  return useMemo(() => ({
    messages,
    isStreaming,
    currentToolCall,
    error,
    activeSessionId,
    sendMessage,
    resetMessages,
  }), [activeSessionId, currentToolCall, error, isStreaming, messages, resetMessages, sendMessage])
}

function parseSseChunk(chunk: string): { event?: string; data: RuntimeChatEvent } | null {
  const lines = chunk.split('\n')
  let eventName = ''
  let dataLine = ''

  for (const line of lines) {
    if (line.startsWith('event:')) {
      eventName = line.slice(6).trim()
    }

    if (line.startsWith('data:')) {
      dataLine += line.slice(5).trim()
    }
  }

  if (!dataLine) {
    return null
  }

  const payload = JSON.parse(dataLine) as RuntimeChatEvent
  return {
    event: eventName,
    data: payload,
  }
}
