/**
 * Tasks — LifeOps durable tasks (BUILD_SPEC section 14).
 *
 * The Knowledge-OS task UI is adapted to the canonical LifeOps state machine.
 * The dropdown choices come from the server (GET /tasks/transitions), and
 * LifeOps Core re-validates every one: the UI narrows the choices, it does not
 * decide them.
 */

import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckSquare, Loader2, Plus, ShieldCheck } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { QueryError } from '@/components/QueryError'
import { cn } from '@/lib/utils'
import {
  LifeOpsError,
  TASK_STATE_LABELS,
  errorMessage,
  systemApi,
  tasksApi,
  type Task,
  type TaskState,
} from '@/services/lifeops'

const STATE_TONE: Record<TaskState, string> = {
  CAPTURED: 'text-muted-foreground',
  PLANNED: 'text-muted-foreground',
  READY: 'text-blue-500',
  EXECUTING: 'text-blue-500',
  WAITING_EXTERNAL: 'text-amber-500',
  NEEDS_APPROVAL: 'text-amber-600',
  VERIFYING: 'text-violet-500',
  COMPLETED: 'text-green-600',
  BLOCKED: 'text-red-500',
  FAILED: 'text-red-600',
  CANCELLED: 'text-muted-foreground line-through',
}

const PRIORITY_TONE: Record<string, string> = {
  urgent: 'border-l-red-500',
  high: 'border-l-orange-500',
  medium: 'border-l-yellow-500',
  low: 'border-l-green-500',
}

const FILTERS: Array<{ id: string; label: string; states?: TaskState[] }> = [
  { id: 'open', label: 'Open' },
  { id: 'attention', label: 'Needs attention', states: ['NEEDS_APPROVAL', 'BLOCKED', 'FAILED'] },
  { id: 'active', label: 'Active', states: ['READY', 'EXECUTING', 'WAITING_EXTERNAL', 'VERIFYING'] },
  { id: 'done', label: 'Completed', states: ['COMPLETED', 'CANCELLED'] },
  { id: 'all', label: 'All' },
]

const CLOSED: TaskState[] = ['COMPLETED', 'CANCELLED']

function TaskCard({
  task,
  nextStates,
  onTransition,
  pending,
  error,
}: {
  task: Task
  /** States the server-served machine permits from here; null when unknown. */
  nextStates: TaskState[] | null
  onTransition: (state: TaskState) => void
  pending: boolean
  error: string | null
}) {
  return (
    <div
      className={cn(
        'rounded-lg border border-l-4 border-border/60 bg-card px-4 py-3',
        PRIORITY_TONE[task.priority] ?? 'border-l-border',
      )}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <p className="font-medium">{task.title}</p>
          {task.description && (
            <p className="mt-1 text-sm text-muted-foreground">{task.description}</p>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span className={cn('font-medium', STATE_TONE[task.state])}>
              {TASK_STATE_LABELS[task.state]}
            </span>
            <span>{task.priority}</span>
            {task.created_by_client && <span>via {task.created_by_client}</span>}
            {task.verification_required && (
              <span className="inline-flex items-center gap-1 text-violet-500">
                <ShieldCheck className="h-3 w-3" />
                verification required
              </span>
            )}
          </div>
        </div>

        {nextStates !== null && nextStates.length > 0 && (
          <select
            className="shrink-0 rounded-md border border-border bg-background px-2 py-1 text-xs"
            value=""
            disabled={pending}
            onChange={(event) => {
              const next = event.target.value as TaskState
              if (next) onTransition(next)
            }}
            aria-label={`Change state of ${task.title}`}
          >
            <option value="">Move to…</option>
            {nextStates.map((state) => (
              <option key={state} value={state}>
                {TASK_STATE_LABELS[state]}
              </option>
            ))}
          </select>
        )}
      </div>

      {error && (
        <p className="mt-2 rounded border border-red-300 bg-red-50 px-2 py-1 text-xs text-red-700">
          {error}
        </p>
      )}
    </div>
  )
}

export function LifeOpsTasksPage() {
  const queryClient = useQueryClient()
  const [filter, setFilter] = useState('open')
  const [newTitle, setNewTitle] = useState('')
  const [transitionErrors, setTransitionErrors] = useState<Record<string, string>>({})

  const tasksQuery = useQuery({
    queryKey: ['lifeops', 'tasks'],
    queryFn: () => tasksApi.list({ limit: 200 }),
  })

  // The transition table comes from the server (GET /tasks/transitions) so the
  // UI offers what the machine currently permits instead of mirroring a
  // hardcoded copy. Display only — the server still validates every change.
  const transitionsQuery = useQuery({
    queryKey: ['lifeops', 'task-transitions'],
    queryFn: () => systemApi.getTransitions(),
    staleTime: 60_000,
  })

  const createTask = useMutation({
    mutationFn: (title: string) => tasksApi.create({ title }),
    onSuccess: () => {
      setNewTitle('')
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'tasks'] })
    },
  })

  const transition = useMutation({
    mutationFn: ({ id, state }: { id: string; state: TaskState }) =>
      tasksApi.update(id, { state }),
    onSuccess: (_data, variables) => {
      setTransitionErrors((prev) => {
        const next = { ...prev }
        delete next[variables.id]
        return next
      })
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'tasks'] })
    },
    onError: (error, variables) => {
      // LifeOps refused the transition. Surface its reason rather than
      // optimistically showing a state the server rejected.
      const message =
        error instanceof LifeOpsError ? error.message : 'Could not update the task.'
      setTransitionErrors((prev) => ({ ...prev, [variables.id]: message }))
    },
  })

  const tasks = tasksQuery.data?.tasks ?? []

  const visible = useMemo(() => {
    const active = FILTERS.find((f) => f.id === filter)
    if (!active || active.id === 'all') return tasks
    if (active.id === 'open') return tasks.filter((t) => !CLOSED.includes(t.state))
    return tasks.filter((t) => active.states?.includes(t.state))
  }, [tasks, filter])

  if (tasksQuery.isError) {
    return (
      <div className="p-8">
        <QueryError message={errorMessage(tasksQuery.error)} onRetry={() => void tasksQuery.refetch()} />
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <CheckSquare className="h-5 w-5" />
            Tasks
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Durable work held by LifeOps. Shared with Hermes and every other
            connected client.
          </p>
        </div>
      </header>

      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          const title = newTitle.trim()
          if (title) createTask.mutate(title)
        }}
      >
        <Input
          value={newTitle}
          onChange={(event) => setNewTitle(event.target.value)}
          placeholder="Capture a task…"
          aria-label="New task title"
        />
        <Button type="submit" disabled={!newTitle.trim() || createTask.isPending}>
          {createTask.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Plus className="h-4 w-4" />
          )}
          <span className="ml-1">Capture</span>
        </Button>
      </form>

      {createTask.isError ? (
        <p
          role="alert"
          className="rounded-lg border border-red-300/60 bg-red-50 px-4 py-2 text-sm text-red-700 dark:border-red-800/60 dark:bg-red-950/40 dark:text-red-300"
        >
          The task was not captured: {errorMessage(createTask.error)}
        </p>
      ) : null}

      <div className="flex flex-wrap gap-2">
        {FILTERS.map((option) => (
          <button
            key={option.id}
            type="button"
            onClick={() => setFilter(option.id)}
            className={cn(
              'rounded-full border px-3 py-1 text-xs transition-colors',
              filter === option.id
                ? 'border-foreground bg-foreground text-background'
                : 'border-border text-muted-foreground hover:bg-muted',
            )}
          >
            {option.label}
          </button>
        ))}
      </div>

      {tasksQuery.isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading…
        </div>
      ) : visible.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border/60 px-4 py-8 text-center text-sm text-muted-foreground">
          No tasks here.
        </p>
      ) : (
        <div className="space-y-2">
          {transitionsQuery.isLoading && (
            <p className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" />
              Loading allowed transitions…
            </p>
          )}
          {transitionsQuery.isError && (
            <div className="flex items-center justify-between gap-4 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800">
              <span>
                Could not load the allowed transitions, so state changes are
                unavailable. {errorMessage(transitionsQuery.error)}
              </span>
              <button
                type="button"
                className="shrink-0 underline"
                onClick={() => void transitionsQuery.refetch()}
              >
                Retry
              </button>
            </div>
          )}
          {visible.map((task) => (
            <TaskCard
              key={task.id}
              task={task}
              nextStates={transitionsQuery.data?.[task.state] ?? null}
              pending={transition.isPending && transition.variables?.id === task.id}
              error={transitionErrors[task.id] ?? null}
              onTransition={(state) => transition.mutate({ id: task.id, state })}
            />
          ))}
        </div>
      )}
    </div>
  )
}
