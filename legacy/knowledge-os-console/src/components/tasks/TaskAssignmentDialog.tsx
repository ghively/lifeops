import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { 
  Dialog, 
  DialogContent, 
  DialogHeader, 
  DialogTitle, 
  DialogDescription,
  DialogFooter
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { 
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Checkbox } from '@/components/ui/checkbox'
import { tasksApi, agentsApi, objectsApi, type AgentItem, type ObjectItem } from '@/services/api'
import { cn } from '@/lib/utils'

interface TaskAssignmentDialogProps {
  taskId: string
  taskTitle: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

const priorities = [
  { value: 'urgent', label: 'Urgent', color: 'text-red-600 bg-red-50' },
  { value: 'high', label: 'High', color: 'text-orange-600 bg-orange-50' },
  { value: 'medium', label: 'Medium', color: 'text-yellow-600 bg-yellow-50' },
  { value: 'low', label: 'Low', color: 'text-green-600 bg-green-50' },
]

export function TaskAssignmentDialog({ 
  taskId, 
  taskTitle, 
  open, 
  onOpenChange 
}: TaskAssignmentDialogProps) {
  const queryClient = useQueryClient()
  const [selectedAgent, setSelectedAgent] = useState('')
  const [selectedPriority, setSelectedPriority] = useState('medium')
  const [includeContext, setIncludeContext] = useState(true)
  const [additionalObjects, setAdditionalObjects] = useState<string[]>([])

  // Fetch agents
  const { data: agentsData } = useQuery({
    queryKey: ['agents'],
    queryFn: agentsApi.list,
  })
  const agents = agentsData?.agents ?? []

  // Fetch recent objects for context selection
  const { data: recentObjectsData } = useQuery({
    queryKey: ['objects', { limit: 10 }],
    queryFn: () => objectsApi.list({ limit: 10 }),
  })
  const recentObjects = recentObjectsData?.objects ?? []

  // Assign task mutation
  const assignMutation = useMutation({
    mutationFn: (data: {
      taskId: string
      request: {
        agent_name: string
        priority: string
        include_context?: boolean
        additional_context?: string[]
      }
    }) => tasksApi.assign(data.taskId, data.request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      queryClient.invalidateQueries({ queryKey: ['object', taskId] })
      onOpenChange(false)
    },
  })

  const handleAssign = () => {
    if (!selectedAgent) return

    assignMutation.mutate({
      taskId,
      request: {
        agent_name: selectedAgent,
        priority: selectedPriority,
        include_context: includeContext,
        additional_context: additionalObjects.length > 0 ? additionalObjects : undefined,
      },
    })
  }

  const toggleAdditionalObject = (objectId: string) => {
    setAdditionalObjects(prev => 
      prev.includes(objectId)
        ? prev.filter(id => id !== objectId)
        : [...prev, objectId]
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Assign Task</DialogTitle>
          <DialogDescription>
            Assign "{taskTitle}" to an agent with the appropriate context.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Agent Selection */}
          <div className="space-y-2">
            <Label>Assign to Agent</Label>
            <Select value={selectedAgent} onValueChange={setSelectedAgent}>
              <SelectTrigger>
                <SelectValue placeholder="Select an agent" />
              </SelectTrigger>
              <SelectContent>
                {agents.map((agent: AgentItem) => (
                  <SelectItem key={agent.id} value={agent.name}>
                    <div className="flex items-center gap-2">
                      <span>🤖</span>
                      <span>@{agent.name}</span>
                      {agent.capabilities && (
                        <span className="text-muted-foreground text-xs">
                          ({agent.capabilities.slice(0, 2).join(', ')})
                        </span>
                      )}
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Priority Selection */}
          <div className="space-y-2">
            <Label>Priority</Label>
            <div className="grid grid-cols-4 gap-2">
              {priorities.map((priority) => (
                <button
                  key={priority.value}
                  onClick={() => setSelectedPriority(priority.value)}
                  className={cn(
                    'px-3 py-2 rounded-md text-sm font-medium transition-colors',
                    selectedPriority === priority.value
                      ? priority.color
                      : 'bg-muted hover:bg-muted/80'
                  )}
                >
                  {priority.label}
                </button>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              {selectedPriority === 'low' 
                ? 'Low priority tasks are added to HEARTBEAT.md for background processing.'
                : 'Medium/High/Urgent tasks are sent directly to the agent via API.'}
            </p>
          </div>

          {/* Context Options */}
          <div className="space-y-3">
            <div className="flex items-center space-x-2">
              <Checkbox
                id="includeContext"
                checked={includeContext}
                onCheckedChange={(checked) => setIncludeContext(checked as boolean)}
              />
              <Label htmlFor="includeContext" className="cursor-pointer">
                Include relevant context automatically
              </Label>
            </div>
            <p className="text-xs text-muted-foreground ml-6">
              This includes: parent object, linked objects, related files, agent memories, and recent chat.
            </p>
          </div>

          {/* Additional Context Objects */}
          {includeContext && recentObjects.length > 0 && (
            <div className="space-y-2">
              <Label>Additional Context (optional)</Label>
              <p className="text-xs text-muted-foreground">
                Select additional objects to include in the context:
              </p>
              <div className="max-h-40 overflow-y-auto border rounded-md p-2 space-y-1">
                {recentObjects
                  .filter((obj: ObjectItem) => obj.id !== taskId)
                  .slice(0, 10)
                  .map((obj: ObjectItem) => (
                    <div key={obj.id} className="flex items-center space-x-2">
                      <Checkbox
                        id={`obj-${obj.id}`}
                        checked={additionalObjects.includes(obj.id)}
                        onCheckedChange={() => toggleAdditionalObject(obj.id)}
                      />
                      <Label htmlFor={`obj-${obj.id}`} className="cursor-pointer text-sm truncate">
                        {obj.icon && <span className="mr-1">{obj.icon}</span>}
                        {obj.title}
                      </Label>
                    </div>
                  ))}
              </div>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button 
            onClick={handleAssign}
            disabled={!selectedAgent || assignMutation.isPending}
          >
            {assignMutation.isPending ? 'Assigning...' : 'Assign Task'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
