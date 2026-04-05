import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bot, Clock3, Loader2, PencilLine, Plus, Rocket, Sparkles, Trash2, Webhook } from 'lucide-react'

import { CLIAgentStatus } from '@/components/agents/CLIAgentStatus'
import { MarkdownEditor, type AgentFileTab } from '@/components/agents/MarkdownEditor'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { agentRuntimeApi, agentsApi, type AgentFile } from '@/services/api'

const DEFAULT_FILE: AgentFileTab = 'AGENT.md'
type DetailTab = 'identity' | 'schedule' | 'webhooks'

export function AgentsPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [newAgentId, setNewAgentId] = useState('')
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>('blank')
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null)
  const [selectedFile, setSelectedFile] = useState<AgentFile['name']>(DEFAULT_FILE)
  const [draftContent, setDraftContent] = useState('')
  const [savedContent, setSavedContent] = useState('')
  const [agentPendingDelete, setAgentPendingDelete] = useState<string | null>(null)
  const [detailTab, setDetailTab] = useState<DetailTab>('identity')
  const [scheduleName, setScheduleName] = useState('')
  const [scheduleCron, setScheduleCron] = useState('every 1 days')
  const [scheduleTaskType, setScheduleTaskType] = useState<'periodic_research' | 'memory_curation' | 'data_cleanup' | 'webhook_triggered'>('periodic_research')
  const [schedulePrompt, setSchedulePrompt] = useState('')
  const [webhookName, setWebhookName] = useState('')
  const [webhookEventType, setWebhookEventType] = useState('external.trigger')

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

  const templatesQuery = useQuery({
    queryKey: ['runtime-agent-templates'],
    queryFn: agentRuntimeApi.listTemplates,
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

  const scheduledTasksQuery = useQuery({
    queryKey: ['runtime-agent-scheduled-tasks', selectedAgentId],
    queryFn: () => agentRuntimeApi.listScheduledTasks(selectedAgentId!),
    enabled: !!selectedAgentId,
  })

  const webhooksQuery = useQuery({
    queryKey: ['runtime-agent-webhooks', selectedAgentId],
    queryFn: () => agentRuntimeApi.listWebhooks(selectedAgentId!),
    enabled: !!selectedAgentId,
  })

  useEffect(() => {
    const nextContent = fileQuery.data?.content || ''
    setDraftContent(nextContent)
    setSavedContent(nextContent)
  }, [fileQuery.data?.content, selectedAgentId, selectedFile])

  const createAgentMutation = useMutation({
    mutationFn: ({ agentId, templateId }: { agentId: string; templateId?: string | null }) => agentRuntimeApi.createAgent(agentId, templateId),
    onSuccess: (createdAgent) => {
      setNewAgentId('')
      setSelectedTemplateId('blank')
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

  const createScheduledTaskMutation = useMutation({
    mutationFn: () => agentRuntimeApi.createScheduledTask({
      agent_id: selectedAgentId!,
      name: scheduleName || `${scheduleTaskType}-${selectedAgentId}`,
      cron_expression: scheduleCron,
      task_type: scheduleTaskType,
      config: schedulePrompt ? { prompt: schedulePrompt } : {},
      enabled: true,
    }),
    onSuccess: () => {
      setScheduleName('')
      setSchedulePrompt('')
      queryClient.invalidateQueries({ queryKey: ['runtime-agent-scheduled-tasks', selectedAgentId] })
    },
  })

  const deleteScheduledTaskMutation = useMutation({
    mutationFn: (taskId: string) => agentRuntimeApi.deleteScheduledTask(taskId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['runtime-agent-scheduled-tasks', selectedAgentId] }),
  })

  const runScheduledTaskMutation = useMutation({
    mutationFn: (taskId: string) => agentRuntimeApi.runScheduledTaskNow(taskId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['runtime-agent-scheduled-tasks', selectedAgentId] }),
  })

  const curateMemoryMutation = useMutation({
    mutationFn: (agentId: string) => agentRuntimeApi.curateMemory(agentId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['runtime-agent-file', selectedAgentId, 'MEMORY.md'] }),
  })

  const createWebhookMutation = useMutation({
    mutationFn: () => agentRuntimeApi.createWebhook({ agent_id: selectedAgentId!, name: webhookName, event_type: webhookEventType }),
    onSuccess: () => {
      setWebhookName('')
      setWebhookEventType('external.trigger')
      queryClient.invalidateQueries({ queryKey: ['runtime-agent-webhooks', selectedAgentId] })
    },
  })

  const deleteWebhookMutation = useMutation({
    mutationFn: (webhookId: string) => agentRuntimeApi.deleteWebhook(webhookId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['runtime-agent-webhooks', selectedAgentId] }),
  })

  const isDirty = draftContent !== savedContent

  const handleCreateAgent = () => {
    const trimmed = newAgentId.trim()
    if (!trimmed) {
      return
    }
    createAgentMutation.mutate({ agentId: trimmed, templateId: selectedTemplateId === 'blank' ? null : selectedTemplateId })
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
          <Select value={selectedTemplateId} onValueChange={setSelectedTemplateId}>
            <SelectTrigger className="sm:w-56">
              <SelectValue placeholder="Template" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="blank">Blank template</SelectItem>
              {(templatesQuery.data?.templates || []).map((template) => (
                <SelectItem key={template.id} value={template.id}>
                  {template.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
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
            {selectedAgentId ? (
              <div className="flex flex-wrap gap-2 pt-2">
                <Button variant={detailTab === 'identity' ? 'default' : 'outline'} size="sm" onClick={() => setDetailTab('identity')}>
                  <PencilLine className="mr-2 h-4 w-4" />
                  Identity
                </Button>
                <Button variant={detailTab === 'schedule' ? 'default' : 'outline'} size="sm" onClick={() => setDetailTab('schedule')}>
                  <Clock3 className="mr-2 h-4 w-4" />
                  Schedule
                </Button>
                <Button variant={detailTab === 'webhooks' ? 'default' : 'outline'} size="sm" onClick={() => setDetailTab('webhooks')}>
                  <Webhook className="mr-2 h-4 w-4" />
                  Webhooks
                </Button>
                <Button variant="outline" size="sm" onClick={() => selectedAgentId && curateMemoryMutation.mutate(selectedAgentId)} disabled={curateMemoryMutation.isPending}>
                  <Sparkles className="mr-2 h-4 w-4" />
                  Curate Memory
                </Button>
              </div>
            ) : null}
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
            ) : detailTab === 'schedule' ? (
              <div className="space-y-4">
                <div className="grid gap-3 md:grid-cols-2">
                  <Input value={scheduleName} onChange={(event) => setScheduleName(event.target.value)} placeholder="Task name" />
                  <Input value={scheduleCron} onChange={(event) => setScheduleCron(event.target.value)} placeholder="every 1 days or 0 * * * *" />
                  <Select value={scheduleTaskType} onValueChange={(value) => setScheduleTaskType(value as typeof scheduleTaskType)}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="periodic_research">Periodic Research</SelectItem>
                      <SelectItem value="memory_curation">Memory Curation</SelectItem>
                      <SelectItem value="data_cleanup">Data Cleanup</SelectItem>
                      <SelectItem value="webhook_triggered">Webhook Triggered</SelectItem>
                    </SelectContent>
                  </Select>
                  <Input value={schedulePrompt} onChange={(event) => setSchedulePrompt(event.target.value)} placeholder="Optional prompt" />
                </div>
                <Button onClick={() => createScheduledTaskMutation.mutate()} disabled={!selectedAgentId || createScheduledTaskMutation.isPending}>
                  Add Scheduled Task
                </Button>
                <div className="space-y-3">
                  {(scheduledTasksQuery.data?.tasks || []).map((task) => (
                    <div key={task.id} className="rounded-lg border p-3">
                      <div className="font-medium">{task.name}</div>
                      <div className="mt-1 text-sm text-muted-foreground">{task.task_type} • {task.cron_expression}</div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        Last run: {task.last_run ? new Date(task.last_run).toLocaleString() : 'Never'} • Next run: {task.next_run ? new Date(task.next_run).toLocaleString() : 'Pending'}
                      </div>
                      <div className="mt-3 flex gap-2">
                        <Button size="sm" variant="outline" onClick={() => runScheduledTaskMutation.mutate(task.id)}>Run now</Button>
                        <Button size="sm" variant="outline" onClick={() => deleteScheduledTaskMutation.mutate(task.id)}>Delete</Button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : detailTab === 'webhooks' ? (
              <div className="space-y-4">
                <div className="grid gap-3 md:grid-cols-2">
                  <Input value={webhookName} onChange={(event) => setWebhookName(event.target.value)} placeholder="Webhook name" />
                  <Input value={webhookEventType} onChange={(event) => setWebhookEventType(event.target.value)} placeholder="Event type" />
                </div>
                <Button onClick={() => createWebhookMutation.mutate()} disabled={!selectedAgentId || !webhookName.trim() || createWebhookMutation.isPending}>
                  Create Webhook
                </Button>
                <div className="space-y-3">
                  {(webhooksQuery.data?.webhooks || []).map((webhook) => (
                    <div key={webhook.id} className="rounded-lg border p-3">
                      <div className="font-medium">{webhook.name}</div>
                      <div className="mt-1 break-all text-xs text-muted-foreground">/api/v1/webhooks/incoming/{webhook.url_path}</div>
                      <div className="mt-1 text-xs text-muted-foreground">Secret: {webhook.secret}</div>
                      <div className="mt-1 text-xs text-muted-foreground">Event: {webhook.event_type}</div>
                      <Button size="sm" variant="outline" className="mt-3" onClick={() => deleteWebhookMutation.mutate(webhook.id)}>
                        Delete
                      </Button>
                    </div>
                  ))}
                </div>
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
