import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Bot, Loader2, MessageSquarePlus, Send, Trash2, Wrench } from 'lucide-react'

import { ApprovalDialog } from '@/components/agents/ApprovalDialog'
import { MarkdownRenderer } from '@/components/agents/MarkdownRenderer'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useAgentChat } from '@/hooks/useAgentChat'
import { agentRuntimeApi, agentsApi, type AgentApprovalRequest } from '@/services/api'
import { useWebSocketStore } from '@/stores/websocket'
import { cn } from '@/lib/utils'

function getCurrentUserId() {
  const token = localStorage.getItem('access_token')
  if (!token) {
    return null
  }
  try {
    const payload = JSON.parse(window.atob(token.split('.')[1] || ''))
    return typeof payload.sub === 'string' ? payload.sub : null
  } catch {
    return null
  }
}

export function AgentChatPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [message, setMessage] = useState('')
  const [selectedSessionId, setSelectedSessionId] = useState<string | null | undefined>(undefined)
  const [pendingApproval, setPendingApproval] = useState<AgentApprovalRequest | null>(null)
  const scrollerRef = useRef<HTMLDivElement | null>(null)
  const connect = useWebSocketStore((state) => state.connect)
  const sendWebSocket = useWebSocketStore((state) => state.send)
  const isWebSocketConnected = useWebSocketStore((state) => state.isConnected)
  const lastWebSocketMessage = useWebSocketStore((state) => state.lastMessage)
  const currentUserId = getCurrentUserId()

  const decodedAgentId = id ? decodeURIComponent(id) : ''

  const agentsQuery = useQuery({
    queryKey: ['agents'],
    queryFn: agentsApi.list,
  })

  const sessionsQuery = useQuery({
    queryKey: ['runtime-agent-sessions', decodedAgentId],
    queryFn: () => agentRuntimeApi.getAgentSessions(decodedAgentId || undefined),
    enabled: !!decodedAgentId,
  })

  useEffect(() => {
    if (!decodedAgentId && agentsQuery.data?.agents?.[0]?.name) {
      navigate(`/agents/${encodeURIComponent(agentsQuery.data.agents[0].name)}/chat`, { replace: true })
    }
  }, [agentsQuery.data?.agents, decodedAgentId, navigate])

  useEffect(() => {
    if (!sessionsQuery.data?.sessions) {
      return
    }

    if (selectedSessionId !== undefined) {
      return
    }

    setSelectedSessionId(sessionsQuery.data.sessions[0]?.id || null)
  }, [selectedSessionId, sessionsQuery.data?.sessions])

  const sessionMessagesQuery = useQuery({
    queryKey: ['runtime-session-messages', selectedSessionId],
    queryFn: () => agentRuntimeApi.getSessionMessages(selectedSessionId!),
    enabled: !!selectedSessionId,
  })

  const { messages, isStreaming, currentToolCall, error, activeSessionId, sendMessage, resetMessages } = useAgentChat({
    agentId: decodedAgentId,
    sessionId: selectedSessionId,
    initialMessages: sessionMessagesQuery.data?.messages || [],
  })

  useEffect(() => {
    if (!activeSessionId || activeSessionId === selectedSessionId) {
      return
    }

    setSelectedSessionId(activeSessionId)
    queryClient.invalidateQueries({ queryKey: ['runtime-agent-sessions', decodedAgentId] })
  }, [activeSessionId, decodedAgentId, queryClient, selectedSessionId])

  useEffect(() => {
    connect()
  }, [connect])

  useEffect(() => {
    if (!isWebSocketConnected || !currentUserId) {
      return
    }
    sendWebSocket({ type: 'subscribe', data: { channels: [`agent-approval:${currentUserId}`] } })
  }, [currentUserId, isWebSocketConnected, sendWebSocket])

  useEffect(() => {
    const message = lastWebSocketMessage as { type?: string; data?: AgentApprovalRequest } | null
    if (message?.type === 'agent.approval_required' && message.data) {
      setPendingApproval(message.data)
    }
  }, [lastWebSocketMessage])

  useEffect(() => {
    const viewport = scrollerRef.current?.querySelector('[data-radix-scroll-area-viewport]') as HTMLDivElement | null
    if (viewport) {
      viewport.scrollTop = viewport.scrollHeight
    }
  }, [messages, currentToolCall])

  const selectedAgent = useMemo(
    () => agentsQuery.data?.agents.find((agent) => agent.name === decodedAgentId) || null,
    [agentsQuery.data?.agents, decodedAgentId]
  )

  const handleSubmit = async () => {
    const trimmed = message.trim()
    if (!trimmed) {
      return
    }

    setMessage('')
    await sendMessage(trimmed)
    queryClient.invalidateQueries({ queryKey: ['runtime-agent-sessions', decodedAgentId] })
  }

  const handleDeleteSession = async (sessionId: string) => {
    await agentRuntimeApi.deleteSession(sessionId)
    if (selectedSessionId === sessionId) {
      setSelectedSessionId(null)
      resetMessages([])
    }
    queryClient.invalidateQueries({ queryKey: ['runtime-agent-sessions', decodedAgentId] })
  }

  const startNewSession = () => {
    setSelectedSessionId(null)
    resetMessages([])
  }

  const handleApprovalDecision = (approved: boolean) => {
    if (!pendingApproval) {
      return
    }
    sendWebSocket({
      type: 'agent.approval_response',
      data: {
        request_id: pendingApproval.request_id,
        approved,
      },
    })
    setPendingApproval(null)
  }

  return (
    <div className="mx-auto flex h-full max-w-7xl flex-col gap-6 px-4 py-6 sm:px-6 sm:py-8">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold">
            <Bot className="h-6 w-6" />
            Agent Chat
          </h1>
          <p className="mt-1 text-muted-foreground">Stream responses from runtime agents and inspect tool activity in real time.</p>
        </div>

        <div className="flex w-full flex-col gap-2 sm:flex-row lg:w-auto">
          <Select value={decodedAgentId} onValueChange={(value) => navigate(`/agents/${encodeURIComponent(value)}/chat`)}>
            <SelectTrigger className="sm:w-72">
              <SelectValue placeholder="Select an agent" />
            </SelectTrigger>
            <SelectContent>
              {(agentsQuery.data?.agents || []).map((agent) => (
                <SelectItem key={agent.name} value={agent.name}>
                  {agent.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Button variant="outline" onClick={startNewSession}>
            <MessageSquarePlus className="mr-2 h-4 w-4" />
            New Session
          </Button>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 gap-6 xl:grid-cols-[18rem_minmax(0,1fr)]">
        <Card className="min-h-[24rem]">
          <CardHeader>
            <CardTitle className="text-lg">Sessions</CardTitle>
            <CardDescription>{sessionsQuery.data?.sessions.length || 0} saved conversation threads.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {sessionsQuery.isLoading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading sessions...
              </div>
            ) : (
              <>
                <Button variant={!selectedSessionId ? 'default' : 'outline'} className="w-full justify-start" onClick={startNewSession}>
                  <MessageSquarePlus className="mr-2 h-4 w-4" />
                  New unsaved session
                </Button>

                <div className="space-y-2">
                  {(sessionsQuery.data?.sessions || []).map((session) => (
                    <div
                      key={session.id}
                      className={cn(
                        'rounded-lg border p-3',
                        session.id === selectedSessionId ? 'border-primary bg-primary/5' : 'hover:bg-muted/60'
                      )}
                    >
                      <button
                        type="button"
                        className="w-full text-left"
                        onClick={() => setSelectedSessionId(session.id)}
                      >
                        <div className="truncate font-medium">{session.title || 'Untitled session'}</div>
                        <div className="mt-1 text-xs text-muted-foreground">
                          {new Date(session.updated_at).toLocaleString()} • {session.message_count} messages
                        </div>
                      </button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="mt-2"
                        onClick={() => void handleDeleteSession(session.id)}
                      >
                        <Trash2 className="h-4 w-4 text-red-600" />
                      </Button>
                    </div>
                  ))}
                </div>
              </>
            )}
          </CardContent>
        </Card>

        <Card className="flex min-h-[38rem] flex-col">
          <CardHeader className="border-b">
            <CardTitle className="text-lg">{selectedAgent?.name || decodedAgentId || 'Agent'}</CardTitle>
            <CardDescription>
              {currentToolCall
                ? `Using ${currentToolCall}`
                : selectedAgent?.description || 'The assistant will stream text and tool events here.'}
            </CardDescription>
          </CardHeader>

          <CardContent className="flex min-h-0 flex-1 flex-col p-0">
            <ScrollArea ref={scrollerRef} className="min-h-0 flex-1 px-4 py-4 sm:px-6">
              <div className="space-y-4">
                {messages.length === 0 ? (
                  <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
                    Start a new conversation with {decodedAgentId || 'an agent'}.
                  </div>
                ) : (
                  messages.map((item) => (
                    <div
                      key={item.id}
                      className={cn('flex', item.role === 'user' ? 'justify-end' : 'justify-start')}
                    >
                      <div
                        className={cn(
                          'max-w-[85%] rounded-2xl px-4 py-3 text-sm shadow-sm',
                          item.role === 'user' && 'bg-primary text-primary-foreground',
                          item.role === 'assistant' && 'bg-muted',
                          item.role === 'tool' && 'border border-sky-200 bg-sky-50 text-sky-950',
                          item.role === 'subagent' && 'border border-emerald-200 bg-emerald-50 text-emerald-950',
                          item.role === 'thinking' && 'border border-amber-200 bg-amber-50 text-amber-950',
                          item.role === 'error' && 'border border-red-200 bg-red-50 text-red-900'
                        )}
                      >
                        {item.role === 'user' ? (
                          <div className="whitespace-pre-wrap">{item.content}</div>
                        ) : item.role === 'tool' ? (
                          <div>
                            <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em]">
                              <Wrench className="h-3.5 w-3.5" />
                              {item.toolName || 'Tool'}
                              {item.status === 'streaming' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                            </div>
                            <MarkdownRenderer content={item.content} />
                          </div>
                        ) : item.role === 'subagent' ? (
                          <div>
                            <div className="mb-2 text-xs font-semibold uppercase tracking-[0.16em]">Sub-Agent</div>
                            <MarkdownRenderer content={item.content} />
                          </div>
                        ) : (
                          <MarkdownRenderer content={item.content} />
                        )}

                        <div className="mt-2 text-[11px] opacity-70">
                          {new Date(item.createdAt).toLocaleTimeString()}
                        </div>
                      </div>
                    </div>
                  ))
                )}

                {isStreaming && currentToolCall ? (
                  <div className="flex justify-start">
                    <div className="inline-flex items-center gap-2 rounded-full border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-900">
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      {currentToolCall}
                    </div>
                  </div>
                ) : null}
              </div>
            </ScrollArea>

            <div className="border-t p-4 sm:p-6">
              {error ? <div className="mb-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900">{error}</div> : null}
              <div className="flex flex-col gap-3 sm:flex-row">
                <Input
                  value={message}
                  onChange={(event) => setMessage(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && !event.shiftKey) {
                      event.preventDefault()
                      void handleSubmit()
                    }
                  }}
                  placeholder={decodedAgentId ? `Message ${decodedAgentId}...` : 'Select an agent to begin'}
                  disabled={!decodedAgentId || isStreaming}
                />
                <Button onClick={() => void handleSubmit()} disabled={!message.trim() || !decodedAgentId || isStreaming}>
                  {isStreaming ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}
                  Send
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
      <ApprovalDialog approval={pendingApproval} open={!!pendingApproval} onDecision={handleApprovalDecision} />
    </div>
  )
}
