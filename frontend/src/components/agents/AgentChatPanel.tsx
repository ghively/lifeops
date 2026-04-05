import { useState, useRef, useEffect } from 'react'
import { X, Send, Bot, User, Loader2, Circle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Input } from '@/components/ui/input'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { agentsApi, type AgentItem, type ChatMessage } from '@/services/api'
import { useWebSocket } from '@/hooks/useWebSocket'
import { cn } from '@/lib/utils'

interface AgentChatPanelProps {
  agent: AgentItem | null
  isOpen: boolean
  onClose: () => void
}

export function AgentChatPanel({ agent, isOpen, onClose }: AgentChatPanelProps) {
  const [message, setMessage] = useState('')
  const [sessionId] = useState(() => `ui-${Math.random().toString(36).slice(2, 10)}`)
  const scrollRef = useRef<HTMLDivElement>(null)
  const queryClient = useQueryClient()

  // Fetch chat history
  const { data: chatHistoryData, isLoading: historyLoading } = useQuery({
    queryKey: ['chat-history', agent?.name],
    queryFn: () => {
      if (!agent) {
        return Promise.resolve({ messages: [] as ChatMessage[] })
      }
      return agentsApi.getChatHistory(agent.name, sessionId)
    },
    enabled: !!agent && isOpen,
    refetchInterval: 5000, // Poll every 5 seconds
  })
  const chatHistory = chatHistoryData?.messages ?? []

  // WebSocket for real-time updates
  const { lastMessage, connectionStatus } = useWebSocket(
    agent
      ? `${(import.meta.env.VITE_API_URL || window.location.origin).replace(/^http/, 'ws')}/ws/agents/${agent.name}`
      : null
  )

  // Send message mutation
  const sendMessageMutation = useMutation({
    mutationFn: (content: string) => {
      if (!agent) throw new Error('No agent selected')
      return agentsApi.chat(agent.name, content, sessionId)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chat-history', agent?.name] })
      setMessage('')
    },
  })

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [chatHistory, lastMessage])

  // Handle incoming WebSocket messages
  useEffect(() => {
    if (lastMessage) {
      try {
        const data = JSON.parse(lastMessage.data)
        if (data.type === 'chat.message' || data.type === 'agent.status_changed' || data.type === 'agent.current_action') {
          queryClient.invalidateQueries({ queryKey: ['chat-history', agent?.name] })
        }
      } catch {
        // Ignore parsing errors
      }
    }
  }, [lastMessage, agent?.name, queryClient])

  const handleSend = () => {
    if (!message.trim() || !agent) return
    sendMessageMutation.mutate(message)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const getStatusColor = (status: AgentItem['status']) => {
    switch (status) {
      case 'active':
      case 'busy':
      case 'working': return 'text-blue-500 animate-pulse'
      case 'idle': return 'text-green-500'
      case 'error': return 'text-red-500'
      case 'offline': return 'text-gray-400'
      default: return 'text-gray-400'
    }
  }

  const getStatusText = (status: AgentItem['status']) => {
    switch (status) {
      case 'active':
      case 'busy':
      case 'working': return 'Busy'
      case 'idle': return 'Idle'
      case 'error': return 'Error'
      case 'offline': return 'Offline'
      default: return 'Unknown'
    }
  }

  if (!isOpen || !agent) return null

  return (
    <div className="fixed inset-x-0 bottom-0 top-16 z-50 flex flex-col border-t border-border bg-background shadow-xl sm:inset-y-0 sm:left-auto sm:top-0 sm:w-96 sm:border-l sm:border-t-0">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-border bg-muted/50">
        <div className="flex items-center gap-3">
          <div className="relative">
            <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
              <Bot className="w-5 h-5 text-primary" />
            </div>
            <Circle 
              className={cn(
                "w-3 h-3 absolute -bottom-0.5 -right-0.5 fill-current",
                getStatusColor(agent.status)
              )} 
            />
          </div>
          <div>
            <h3 className="font-semibold text-sm">{agent.name}</h3>
            <p className="flex items-center gap-1 text-xs text-muted-foreground">
              <span className={getStatusColor(agent.status)}>
                {getStatusText(agent.status)}
              </span>
              {agent.current_task && (
                <span className="max-w-[160px] truncate">• {agent.current_task}</span>
              )}
            </p>
          </div>
        </div>
        <Button aria-label="Close chat" variant="ghost" size="icon" onClick={onClose}>
          <X className="w-4 h-4" />
        </Button>
      </div>

      {/* Connection Status */}
      {connectionStatus !== 'connected' && (
        <div className="px-4 py-2 bg-yellow-500/10 text-yellow-600 text-xs flex items-center gap-2">
          <Loader2 className="w-3 h-3 animate-spin" />
          {connectionStatus === 'connecting' ? 'Connecting...' : 'Disconnected'}
        </div>
      )}

      {/* Chat Messages */}
      <ScrollArea ref={scrollRef} className="flex-1 p-4">
        {historyLoading ? (
          <div className="flex items-center justify-center h-full">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        ) : chatHistory.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center text-muted-foreground">
            <Bot className="w-12 h-12 mb-4 opacity-50" />
            <p className="text-sm">Start a conversation with {agent.name}</p>
            <p className="text-xs mt-1">Ask questions, assign tasks, or request updates</p>
          </div>
        ) : (
          <div className="space-y-4">
            {chatHistory.map((msg: ChatMessage) => (
              <div
                key={msg.id}
                className={cn(
                  "flex gap-3",
                  msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'
                )}
              >
                <div className={cn(
                  "w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0",
                  msg.role === 'user' 
                    ? 'bg-primary text-primary-foreground' 
                    : msg.role === 'system'
                    ? 'bg-yellow-500/20 text-yellow-600'
                    : 'bg-primary/10 text-primary'
                )}>
                  {msg.role === 'user' ? (
                    <User className="w-4 h-4" />
                  ) : msg.role === 'system' ? (
                    <span className="text-xs">!</span>
                  ) : (
                    <Bot className="w-4 h-4" />
                  )}
                </div>
                <div className={cn(
                  'max-w-[85%] rounded-lg px-3 py-2 text-sm sm:max-w-[75%]',
                  msg.role === 'user'
                    ? 'bg-primary text-primary-foreground'
                    : msg.role === 'system'
                    ? 'bg-yellow-500/10 text-yellow-700 border border-yellow-500/20'
                    : 'bg-muted'
                )}>
                  <div className="whitespace-pre-wrap">{msg.content}</div>
                  <div className={cn(
                    "text-[10px] mt-1",
                    msg.role === 'user' ? 'text-primary-foreground/60' : 'text-muted-foreground'
                  )}>
                    {new Date(msg.timestamp).toLocaleTimeString()}
                  </div>
                </div>
              </div>
            ))}
            {sendMessageMutation.isPending && (
              <div className="flex gap-3">
                <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
                  <Bot className="w-4 h-4 text-primary" />
                </div>
                <div className="bg-muted rounded-lg px-3 py-2 flex items-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span className="text-sm text-muted-foreground">Thinking...</span>
                </div>
              </div>
            )}
          </div>
        )}
      </ScrollArea>

      {/* Input Area */}
      <div className="p-4 border-t border-border bg-muted/50">
        <div className="flex gap-2">
          <Input
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={`Message ${agent.name}...`}
            disabled={sendMessageMutation.isPending || agent.status === 'offline'}
            className="flex-1"
          />
          <Button 
            onClick={handleSend} 
            disabled={!message.trim() || sendMessageMutation.isPending || agent.status === 'offline'}
            size="icon"
          >
            {sendMessageMutation.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </Button>
        </div>
        {agent.status === 'offline' && (
          <p className="text-xs text-muted-foreground mt-2 text-center">
            Agent is offline. Messages will be queued.
          </p>
        )}
      </div>
    </div>
  )
}
