import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckSquare, Plus, MoreHorizontal, User } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { TaskAssignmentDialog } from '@/components/tasks/TaskAssignmentDialog'
import { tasksApi, objectsApi, type TaskItem } from '@/services/api'
import { cn } from '@/lib/utils'
import { Input } from '@/components/ui/input'
import { useNavigate } from 'react-router-dom'

const priorityColors = {
  urgent: 'border-l-red-500 bg-red-50/50',
  high: 'border-l-orange-500 bg-orange-50/50',
  medium: 'border-l-yellow-500 bg-yellow-50/50',
  low: 'border-l-green-500 bg-green-50/50',
}

const priorityBadges = {
  urgent: 'bg-red-100 text-red-700',
  high: 'bg-orange-100 text-orange-700',
  medium: 'bg-yellow-100 text-yellow-700',
  low: 'bg-green-100 text-green-700',
}

const statusLabels: Record<string, string> = {
  todo: 'To Do',
  'in-progress': 'In Progress',
  blocked: 'Blocked',
  review: 'In Review',
  done: 'Done',
}

const statusColors: Record<string, string> = {
  todo: 'text-gray-500',
  'in-progress': 'text-blue-500',
  blocked: 'text-red-500',
  review: 'text-yellow-500',
  done: 'text-green-500',
}

export function TasksPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [statusFilter, setStatusFilter] = useState<'all' | 'todo' | 'in-progress' | 'blocked' | 'review' | 'done'>('all')
  const [priorityFilter, setPriorityFilter] = useState<'all' | 'urgent' | 'high' | 'medium' | 'low'>('all')
  const [selectedTask, setSelectedTask] = useState<TaskItem | null>(null)
  const [assignmentDialogOpen, setAssignmentDialogOpen] = useState(false)
  const [newTaskTitle, setNewTaskTitle] = useState('')

  // Fetch tasks (objects with type='task')
  const { data: tasksData, isLoading } = useQuery({
    queryKey: ['tasks', { statusFilter, priorityFilter }],
    queryFn: () => tasksApi.list({
      status: statusFilter === 'all' ? undefined : statusFilter,
      priority: priorityFilter === 'all' ? undefined : priorityFilter,
    }),
  })

  const tasks: TaskItem[] = tasksData?.tasks || []
  const byStatus = tasksData?.by_status || {}
  const byPriority = tasksData?.by_priority || {}

  // Create task mutation
  const createTaskMutation = useMutation({
    mutationFn: objectsApi.create,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      setSelectedTask(data as TaskItem)
      setNewTaskTitle('')
    },
  })

  const handleCreateTask = (title = 'New Task') => {
    createTaskMutation.mutate({
      type: 'task',
      title,
      content: '',
      properties: {
        status: 'todo',
        priority: 'medium',
      },
    })
  }

  const handleAssignClick = (task: TaskItem) => {
    setSelectedTask(task)
    setAssignmentDialogOpen(true)
  }

  const handleInlineCreate = () => {
    if (!newTaskTitle.trim()) return
    handleCreateTask(newTaskTitle.trim())
  }

  const statusOptions = useMemo(() => ([
    ['all', tasks.length],
    ['todo', byStatus.todo || 0],
    ['in-progress', byStatus['in-progress'] || 0],
    ['blocked', byStatus.blocked || 0],
    ['review', byStatus.review || 0],
    ['done', byStatus.done || 0],
  ] as const), [byStatus, tasks.length])

  const priorityOptions = useMemo(() => ([
    ['all', tasks.length],
    ['urgent', byPriority.urgent || 0],
    ['high', byPriority.high || 0],
    ['medium', byPriority.medium || 0],
    ['low', byPriority.low || 0],
  ] as const), [byPriority, tasks.length])

  if (isLoading) {
    return (
      <div className="max-w-4xl mx-auto py-8 px-6">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-muted rounded w-1/4" />
          <div className="h-4 bg-muted rounded w-1/2" />
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-20 bg-muted rounded" />
            ))}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto flex max-w-6xl gap-6 px-6 py-8">
      <div className="min-w-0 flex-1">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <CheckSquare className="h-6 w-6" />
            Tasks
          </h1>
          <p className="text-muted-foreground mt-1">
            {tasks.length} tasks • {byStatus.done || 0} completed
          </p>
        </div>
        <Button onClick={() => handleCreateTask()} disabled={createTaskMutation.isPending}>
          <Plus className="h-4 w-4 mr-2" />
          {createTaskMutation.isPending ? 'Creating...' : 'New Task'}
        </Button>
      </div>

      <div className="mb-6 flex gap-2 rounded-lg border bg-card p-3">
        <Input
          value={newTaskTitle}
          onChange={(event) => setNewTaskTitle(event.target.value)}
          onKeyDown={(event) => event.key === 'Enter' && handleInlineCreate()}
          placeholder="Create a task inline..."
        />
        <Button onClick={handleInlineCreate} disabled={createTaskMutation.isPending || !newTaskTitle.trim()}>
          <Plus className="mr-2 h-4 w-4" />
          Add
        </Button>
      </div>

      {/* Filters */}
      <div className="space-y-3 mb-6">
        <div className="flex flex-wrap items-center gap-2">
          {statusOptions.map(([value, count]) => (
            <Button
              key={value}
              variant={statusFilter === value ? 'secondary' : 'ghost'}
              size="sm"
              onClick={() => setStatusFilter(value)}
            >
              {statusLabels[value] || 'All'} ({count})
            </Button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {priorityOptions.map(([value, count]) => (
            <Button
              key={value}
              variant={priorityFilter === value ? 'secondary' : 'ghost'}
              size="sm"
              onClick={() => setPriorityFilter(value)}
            >
              {value === 'all' ? 'All Priorities' : value} ({count})
            </Button>
          ))}
        </div>
      </div>

      {/* Task List */}
      <div className="space-y-2">
        {tasks.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            <CheckSquare className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p>No tasks found</p>
            <p className="text-sm">Create your first task to get started</p>
          </div>
        ) : (
          tasks.map((task) => (
            <div
              key={task.id}
              data-testid="task-row"
              className={cn(
                'p-4 bg-card border rounded-lg border-l-4 hover:shadow-sm transition-shadow cursor-pointer',
                priorityColors[task.properties?.priority || 'medium']
              )}
              onClick={() => setSelectedTask(task)}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="font-medium">{task.title}</h3>
                    <span
                      className={cn(
                        'text-xs px-2 py-0.5 rounded-full font-medium',
                        priorityBadges[task.properties?.priority || 'medium']
                      )}
                    >
                      {task.properties?.priority}
                    </span>
                  </div>
                  
                  <div className="flex items-center gap-4 text-sm">
                    <span className={cn('font-medium', statusColors[task.properties?.status || 'todo'])}>
                      {statusLabels[task.properties?.status || 'todo']}
                    </span>
                    
                    {typeof task.properties?.assigned_to === 'string' && task.properties.assigned_to.length > 0 && (
                      <span className="flex items-center gap-1 text-muted-foreground">
                        <User className="h-3 w-3" />
                        @{String(task.properties.assigned_to)}
                      </span>
                    )}
                    
                    {typeof task.properties?.current_action === 'string' && task.properties.current_action.length > 0 && (
                      <span className="text-blue-600">
                        ⏳ {String(task.properties.current_action)}
                      </span>
                    )}
                    
                    {typeof task.properties?.due_date === 'string' && task.properties.due_date.length > 0 && (
                      <span className="text-muted-foreground">
                        Due {new Date(task.properties.due_date).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                </div>
                
                <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                  {!task.properties?.assigned_to && task.properties?.status !== 'done' && (
                    <Button 
                      variant="ghost" 
                      size="sm"
                      onClick={() => handleAssignClick(task)}
                    >
                      Assign
                    </Button>
                  )}
                  <Button variant="ghost" size="icon">
                    <MoreHorizontal className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
      </div>

      <aside className="sticky top-6 h-fit w-full max-w-sm rounded-xl border bg-card p-5">
        {selectedTask ? (
          <div className="space-y-4">
            <div>
              <div className="mb-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">Task Details</div>
              <h2 className="text-xl font-semibold">{selectedTask.title}</h2>
              <p className="mt-2 whitespace-pre-wrap text-sm text-muted-foreground">
                {selectedTask.content || 'No task description yet.'}
              </p>
            </div>
            <div className="grid gap-3 text-sm">
              <div>
                <div className="text-muted-foreground">Status</div>
                <div>{statusLabels[selectedTask.properties?.status || 'todo']}</div>
              </div>
              <div>
                <div className="text-muted-foreground">Priority</div>
                <div className="capitalize">{selectedTask.properties?.priority || 'medium'}</div>
              </div>
              <div>
                <div className="text-muted-foreground">Assigned To</div>
                <div>{selectedTask.properties?.assigned_to ? `@${String(selectedTask.properties.assigned_to)}` : 'Unassigned'}</div>
              </div>
              <div>
                <div className="text-muted-foreground">Current Action</div>
                <div>{String(selectedTask.properties?.current_action || 'Idle')}</div>
              </div>
            </div>
            <div className="flex gap-2">
              {!selectedTask.properties?.assigned_to && selectedTask.properties?.status !== 'done' && (
                <Button onClick={() => handleAssignClick(selectedTask)}>Assign</Button>
              )}
              <Button variant="outline" onClick={() => navigate(`/object/${selectedTask.id}`)}>
                Open Note
              </Button>
            </div>
          </div>
        ) : (
          <div className="text-sm text-muted-foreground">
            Select a task to inspect its details and assignment state.
          </div>
        )}
      </aside>

      {/* Assignment Dialog */}
      {selectedTask && (
        <TaskAssignmentDialog
          taskId={selectedTask.id}
          taskTitle={selectedTask.title}
          open={assignmentDialogOpen}
          onOpenChange={(open) => {
            setAssignmentDialogOpen(open)
            if (!open) setSelectedTask(null)
          }}
        />
      )}
    </div>
  )
}
