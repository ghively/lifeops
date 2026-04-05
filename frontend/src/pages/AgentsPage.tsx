import { useState } from 'react'
import { Bot, MessageSquare, Loader2, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { agentsApi, type AgentItem } from '@/services/api'
import { AgentChatPanel } from '@/components/agents/AgentChatPanel'
import { cn } from '@/lib/utils'

interface Agent extends AgentItem {
  last_seen?: string
  total_tasks?: number
  completed_tasks?: number
}

const statusColors = {
  active: 'bg-blue-500',
  busy: 'bg-blue-500',
  idle: 'bg-green-500',
  working: 'bg-blue-500',
  error: 'bg-red-500',
  offline: 'bg-gray-400',
}

const statusText = {
  active: 'Active',
  busy: 'Busy',
  idle: 'Idle',
  working: 'Working',
  error: 'Error',
  offline: 'Offline',
}

export function AgentsPage() {
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null)
  const [chatOpen, setChatOpen] = useState(false)
  const queryClient = useQueryClient()

  // Fetch agents
  const { data: agentsData, isLoading, error } = useQuery({
    queryKey: ['agents'],
    queryFn: agentsApi.list,
    refetchInterval: 5000, // Poll every 5 seconds for status updates
  })
  const agents = (agentsData?.agents ?? []) as Agent[]

  // Refresh agents mutation
  const refreshMutation = useMutation({
    mutationFn: () => agentsApi.list(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
    },
  })

  const handleAgentClick = (agent: Agent) => {
    setSelectedAgent(agent)
    setChatOpen(true)
  }

  const handleCloseChat = () => {
    setChatOpen(false)
    setSelectedAgent(null)
  }

  const workingAgents = agents.filter((a: Agent) => ['active', 'busy', 'working'].includes(a.status)).length
  const idleAgents = agents.filter((a: Agent) => a.status === 'idle').length
  const offlineAgents = agents.filter((a: Agent) => a.status === 'offline').length

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-red-500">
        <p>Error loading agents</p>
        <Button variant="outline" onClick={() => refreshMutation.mutate()} className="mt-4">
          <RefreshCw className="h-4 w-4 mr-2" />
          Retry
        </Button>
      </div>
    )
  }

  return (
    <div className="h-full flex">
      <div className={cn(
        'flex-1 overflow-auto p-4 transition-all sm:p-6',
        chatOpen && 'sm:mr-96'
      )}>
        <div className="max-w-5xl mx-auto">
          {/* Header */}
          <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h1 className="text-2xl font-bold flex items-center gap-2">
                <Bot className="h-6 w-6" />
                Agents
              </h1>
              <p className="text-muted-foreground mt-1">
                {agents.length} agent{agents.length !== 1 ? 's' : ''} connected
              </p>
            </div>
            <Button variant="outline" onClick={() => refreshMutation.mutate()} disabled={refreshMutation.isPending}>
              <RefreshCw className={cn("h-4 w-4 mr-2", refreshMutation.isPending && "animate-spin")} />
              Refresh
            </Button>
          </div>

          {/* Stats */}
          <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
            <div className="p-4 bg-card border rounded-lg">
              <div className="text-2xl font-bold">{agents.length}</div>
              <div className="text-sm text-muted-foreground">Total Agents</div>
            </div>
            <div className="p-4 bg-card border rounded-lg">
              <div className="text-2xl font-bold text-blue-500">{workingAgents}</div>
              <div className="text-sm text-muted-foreground">Working</div>
            </div>
            <div className="p-4 bg-card border rounded-lg">
              <div className="text-2xl font-bold text-green-500">{idleAgents}</div>
              <div className="text-sm text-muted-foreground">Idle</div>
            </div>
            <div className="p-4 bg-card border rounded-lg">
              <div className="text-2xl font-bold text-gray-400">{offlineAgents}</div>
              <div className="text-sm text-muted-foreground">Offline</div>
            </div>
          </div>

          {/* Agent List */}
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {agents.length === 0 ? (
              <div className="col-span-2 text-center py-12 text-muted-foreground">
                <Bot className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p className="text-lg font-medium">No agents configured</p>
                <p className="text-sm">Add agents in settings to get started</p>
              </div>
            ) : (
              agents.map((agent: Agent) => (
                <div
                  key={agent.id}
                  data-testid="agent-card"
                  className="p-4 bg-card border rounded-lg hover:shadow-sm transition-shadow cursor-pointer"
                  onClick={() => handleAgentClick(agent)}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
                        <Bot className="h-5 w-5" />
                      </div>
                      <div>
                        <h3 className="font-medium">@{agent.name}</h3>
                        <div className="flex items-center gap-2 text-sm text-muted-foreground">
                          <span className={cn("h-2 w-2 rounded-full", statusColors[agent.status as keyof typeof statusColors])} />
                          <span className="capitalize">{statusText[agent.status as keyof typeof statusText]}</span>
                          {agent.last_seen && (
                            <>
                              <span>•</span>
                              <span>{new Date(agent.last_seen).toLocaleTimeString()}</span>
                            </>
                          )}
                        </div>
                      </div>
                    </div>
                    <Button 
                      variant="ghost" 
                      size="icon"
                      onClick={(e) => {
                        e.stopPropagation()
                        handleAgentClick(agent)
                      }}
                    >
                      <MessageSquare className="h-4 w-4" />
                    </Button>
                  </div>

                  {agent.current_task && (
                    <div className="mt-3 p-2 bg-muted rounded text-sm">
                      <span className="text-muted-foreground">Current task:</span>{' '}
                      <span className="font-medium">{agent.current_task}</span>
                    </div>
                  )}

                  {agent.capabilities && agent.capabilities.length > 0 && (
                    <div className="mt-3">
                      <div className="text-sm text-muted-foreground mb-2">Capabilities</div>
                      <div className="flex flex-wrap gap-2">
                        {agent.capabilities.map((cap: string) => (
                          <span
                            key={cap}
                            className="text-xs px-2 py-1 bg-muted rounded-full"
                          >
                            {cap}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {(agent.total_tasks !== undefined && agent.completed_tasks !== undefined) && (
                    <div className="mt-3 flex items-center gap-4 text-sm text-muted-foreground">
                      <span>Tasks: {agent.completed_tasks}/{agent.total_tasks}</span>
                      {agent.total_tasks > 0 && (
                        <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
                          <div 
                            className="h-full bg-primary rounded-full"
                            style={{ width: `${(agent.completed_tasks / agent.total_tasks) * 100}%` }}
                          />
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Chat Panel */}
      <AgentChatPanel
        agent={selectedAgent}
        isOpen={chatOpen}
        onClose={handleCloseChat}
      />
    </div>
  )
}
