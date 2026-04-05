import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bot, Loader2, PencilLine, Plus, Rocket, Trash2 } from 'lucide-react'

import { CLIAgentStatus } from '@/components/agents/CLIAgentStatus'
import { MarkdownEditor, type AgentFileTab } from '@/components/agents/MarkdownEditor'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { agentRuntimeApi, agentsApi, type AgentFile } from '@/services/api'

const DEFAULT_FILE: AgentFileTab = 'AGENT.md'

export function AgentsPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [newAgentId, setNewAgentId] = useState('')
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null)
  const [selectedFile, setSelectedFile] = useState<AgentFile['name']>(DEFAULT_FILE)
  const [draftContent, setDraftContent] = useState('')
  const [savedContent, setSavedContent] = useState('')
  const [agentPendingDelete, setAgentPendingDelete] = useState<string | null>(null)

  const runtimeAgentsQuery = useQuery({
    queryKey: ['runtime-agents'],
    queryFn: agentRuntimeApi.list,
  })

  const allAgentsQuery = useQuery({
    queryKey: ['agents'],
    queryFn: agentsApi.list,
  })

  const cliStatusQuery = useQuery({
    queryKey: ['runtime-cli-status'],
    queryFn: agentRuntimeApi.getCLIAgentStatus,
  })

  useEffect(() => {
    if (!selectedAgentId && runtimeAgentsQuery.data?.agents?.length) {
      setSelectedAgentId(runtimeAgentsQuery.data.agents[0].id)
    }
  }, [runtimeAgentsQuery.data?.agents, selectedAgentId])

  const selectedAgent = useMemo(
    () => runtimeAgentsQuery.data?.agents.find((agent) => agent.id === selectedAgentId) || null,
    [runtimeAgentsQuery.data?.agents, selectedAgentId]
  )

  const runtimeStatusByName = useMemo(() => {
    return new Map((allAgentsQuery.data?.agents || []).map((agent) => [agent.name, agent]))
  }, [allAgentsQuery.data?.agents])

  const selectedAgentStatus = selectedAgent ? runtimeStatusByName.get(selectedAgent.id) : null

  const fileQuery = useQuery({
    queryKey: ['runtime-agent-file', selectedAgentId, selectedFile],
    queryFn: () => agentRuntimeApi.getAgentFile(selectedAgentId!, selectedFile),
    enabled: !!selectedAgentId,
  })

  useEffect(() => {
    const nextContent = fileQuery.data?.content || ''
    setDraftContent(nextContent)
    setSavedContent(nextContent)
  }, [fileQuery.data?.content, selectedAgentId, selectedFile])

  const createAgentMutation = useMutation({
    mutationFn: (agentId: string) => agentRuntimeApi.createAgent(agentId),
    onSuccess: (createdAgent) => {
      setNewAgentId('')
      setSelectedAgentId(createdAgent.id)
      queryClient.invalidateQueries({ queryKey: ['runtime-agents'] })
      queryClient.invalidateQueries({ queryKey: ['agents'] })
    },
  })

  const saveFileMutation = useMutation({
    mutationFn: ({ agentId, fileName, content }: { agentId: string; fileName: AgentFile['name']; content: string }) =>
      agentRuntimeApi.updateAgentFile(agentId, fileName, content),
    onSuccess: () => {
      setSavedContent(draftContent)
      queryClient.invalidateQueries({ queryKey: ['runtime-agent-file', selectedAgentId, selectedFile] })
    },
  })

  const deleteAgentMutation = useMutation({
    mutationFn: (agentId: string) => agentRuntimeApi.deleteAgent(agentId),
    onSuccess: (_, deletedAgentId) => {
      if (selectedAgentId === deletedAgentId) {
        const remaining = runtimeAgentsQuery.data?.agents.filter((agent) => agent.id !== deletedAgentId) || []
        setSelectedAgentId(remaining[0]?.id || null)
      }
      setAgentPendingDelete(null)
      queryClient.invalidateQueries({ queryKey: ['runtime-agents'] })
      queryClient.invalidateQueries({ queryKey: ['agents'] })
    },
  })

  const isDirty = draftContent !== savedContent

  const handleCreateAgent = () => {
    const trimmed = newAgentId.trim()
    if (!trimmed) {
      return
    }
    createAgentMutation.mutate(trimmed)
  }

  const handleSave = () => {
    if (!selectedAgentId) {
      return
    }
    saveFileMutation.mutate({ agentId: selectedAgentId, fileName: selectedFile, content: draftContent })
  }

  const handleDiscard = () => {
    setDraftContent(savedContent)
  }

  return (
    <div className="mx-auto flex h-full max-w-7xl flex-col gap-6 px-4 py-6 sm:px-6 sm:py-8">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold">
            <Bot className="h-6 w-6" />
            Agents
          </h1>
          <p className="mt-1 text-muted-foreground">Create, edit, and launch runtime agents from their identity files.</p>
        </div>

        <div className="flex w-full flex-col gap-2 sm:flex-row lg:w-auto">
          <Input
            value={newAgentId}
            onChange={(event) => setNewAgentId(event.target.value)}
            placeholder="new-agent-id"
            className="sm:w-64"
          />
          <Button onClick={handleCreateAgent} disabled={!newAgentId.trim() || createAgentMutation.isPending}>
            {createAgentMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-4 w-4" />}
            New Agent
          </Button>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[20rem_minmax(0,1fr)]">
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">CLI Agents</CardTitle>
              <CardDescription>Runtime availability for local CLI-backed tools.</CardDescription>
            </CardHeader>
            <CardContent>
              {cliStatusQuery.isLoading ? <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /> : <CLIAgentStatus status={cliStatusQuery.data} />}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Runtime Agents</CardTitle>
              <CardDescription>{runtimeAgentsQuery.data?.agents.length || 0} agent identities on disk.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {runtimeAgentsQuery.isLoading ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Loading agents...
                </div>
              ) : runtimeAgentsQuery.data?.agents.length ? (
                runtimeAgentsQuery.data.agents.map((agent) => {
                  const status = runtimeStatusByName.get(agent.id)
                  const selected = agent.id === selectedAgentId

                  return (
                    <button
                      key={agent.id}
                      type="button"
                      onClick={() => setSelectedAgentId(agent.id)}
                      className={`w-full rounded-lg border p-3 text-left transition-colors ${selected ? 'border-primary bg-primary/5' : 'hover:bg-muted/60'}`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="font-medium">{agent.id}</div>
                          <div className="mt-1 text-xs text-muted-foreground">{agent.path}</div>
                          {status ? (
                            <div className="mt-2 text-xs text-muted-foreground">
                              Status: <span className="font-medium text-foreground">{status.status}</span>
                            </div>
                          ) : null}
                        </div>
                        <div className="flex shrink-0 items-center gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={(event) => {
                              event.stopPropagation()
                              navigate(`/agents/${encodeURIComponent(agent.id)}/chat`)
                            }}
                          >
                            <Rocket className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={(event) => {
                              event.stopPropagation()
                              setAgentPendingDelete(agent.id)
                            }}
                          >
                            <Trash2 className="h-4 w-4 text-red-600" />
                          </Button>
                        </div>
                      </div>
                    </button>
                  )
                })
              ) : (
                <div className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
                  No runtime agents exist yet. Create one to scaffold `AGENT.md`, `SOUL.md`, `MEMORY.md`, and `TOOLS.md`.
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        <Card className="min-h-[42rem]">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <PencilLine className="h-5 w-5" />
              {selectedAgent ? `${selectedAgent.id} identity files` : 'Agent editor'}
            </CardTitle>
            <CardDescription>
              {selectedAgentStatus
                ? `${selectedAgentStatus.status} • ${selectedAgentStatus.description || 'Runtime identity and tool configuration'}`
                : 'Select a runtime agent to edit its markdown identity files.'}
            </CardDescription>
          </CardHeader>
          <CardContent className="h-[calc(100%-5rem)]">
            {!selectedAgentId ? (
              <div className="flex h-full items-center justify-center rounded-lg border border-dashed text-sm text-muted-foreground">
                Select or create an agent to start editing.
              </div>
            ) : fileQuery.isLoading ? (
              <div className="flex h-full items-center justify-center">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : (
              <MarkdownEditor
                activeFile={selectedFile}
                content={draftContent}
                isDirty={isDirty}
                isSaving={saveFileMutation.isPending}
                onFileChange={(file) => setSelectedFile(file)}
                onChange={setDraftContent}
                onSave={handleSave}
                onDiscard={handleDiscard}
              />
            )}
          </CardContent>
        </Card>
      </div>

      <Dialog open={!!agentPendingDelete} onOpenChange={(open) => !open && setAgentPendingDelete(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete agent</DialogTitle>
            <DialogDescription>
              This removes the runtime agent directory and all four identity files from disk.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAgentPendingDelete(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => agentPendingDelete && deleteAgentMutation.mutate(agentPendingDelete)}
              disabled={deleteAgentMutation.isPending}
            >
              {deleteAgentMutation.isPending ? 'Deleting...' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
