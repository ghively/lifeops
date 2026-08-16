/**
 * Needs Attention — work that cannot proceed without a human
 * (BUILD_SPEC section 12).
 *
 * Only tasks in an attention state are shown: approvals, blocked work, and
 * failures. Routine notifications never appear here — the point of the screen
 * is to minimize interruption, so an empty screen is good news, not a bug.
 *
 * The transition dropdown offers only moves the LifeOps state machine
 * permits, exactly as the Tasks screen does; LifeOps Core re-validates every
 * transition and its refusal is shown verbatim.
 */

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, Loader2, ShieldCheck } from 'lucide-react'

import { QueryError } from '@/components/QueryError'
import { cn } from '@/lib/utils'
import {
  LifeOpsError,
  errorMessage,
  systemApi,
  tasksApi,
  type Task,
  type TaskState,
} from '@/services/lifeops'

type AttentionState = 'NEEDS_APPROVAL' | 'BLOCKED' | 'FAILED'

const ATTENTION_STATES: AttentionState[] = ['NEEDS_APPROVAL', 'BLOCKED', 'FAILED']

/**
 * Why the task needs a human, in one line. `current_action` is what LifeOps
 * was trying to do when it stopped, so it is the most honest explanation
 * available in Phase 1.
 */
function attentionReason(task: Task): string {
  switch (task.state) {
    case 'NEEDS_APPROVAL':
      return task.current_action
        ? `Approve: ${task.current_action}`
        : 'Waiting on your approval to continue.'
    case 'BLOCKED':
      return task.current_action
        ? `Blocked: ${task.current_action}`
        : 'Blocked — Hermes cannot resolve this on its own.'
    case 'FAILED':
      return task.current_action
        ? `Failed: ${task.current_action}`
        : 'The last attempt failed.'
    default:
      return 'Needs your attention.'
  }
}

const STATE_TONE: Record<AttentionState, string> = {
  NEEDS_APPROVAL: 'text-amber-600',
  BLOCKED: 'text-red-500',
  FAILED: 'text-red-600',
}

function AttentionCard({
  task,
  nextStates,
  onTransition,
  pending,
  error,
}: {
  task: Task
  nextStates: TaskState[] | null
  onTransition: (state: TaskState) => void
  pending: boolean
  error: string | null
}) {
  return (
    <div className="rounded-lg border border-l-4 border-l-amber-500 border-border/60 bg-card px-4 py-3">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <p className="font-medium">{task.title}</p>
          <p className={cn('mt-1 text-sm', STATE_TONE[task.state as AttentionState])}>
            {attentionReason(task)}
          </p>
          {task.description && (
            <p className="mt-1 text-sm text-muted-foreground">{task.description}</p>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
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
                {state}
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

export function NeedsAttentionPage() {
  const queryClient = useQueryClient()
  const [transitionErrors, setTransitionErrors] = useState<Record<string, string>>({})

  const tasksQuery = useQuery({
    queryKey: ['lifeops', 'tasks', 'needs-attention'],
    queryFn: () => tasksApi.list({ state: [...ATTENTION_STATES], limit: 200 }),
    refetchInterval: 30_000,
  })

  // The transition table comes from the server (GET /tasks/transitions) so the
  // UI offers what the machine currently permits instead of mirroring a
  // hardcoded copy. Display only — the server still validates every change.
  const transitionsQuery = useQuery({
    queryKey: ['lifeops', 'task-transitions'],
    queryFn: () => systemApi.getTransitions(),
    staleTime: 60_000,
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

  if (tasksQuery.isError) {
    return (
      <div className="p-8">
        <QueryError
          message={errorMessage(tasksQuery.error)}
          onRetry={() => void tasksQuery.refetch()}
        />
      </div>
    )
  }

  const tasks = tasksQuery.data?.tasks ?? []

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-8">
      <header>
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <AlertCircle className="h-5 w-5" />
          Needs Attention
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Only work that genuinely needs a human: approvals, blocked tasks, and
          failures. Everything else keeps moving without interrupting you.
        </p>
      </header>

      {tasksQuery.isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading…
        </div>
      ) : tasks.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border/60 px-4 py-8 text-center text-sm text-muted-foreground">
          Nothing needs your attention right now.
        </p>
      ) : (
        ATTENTION_STATES.map((state) => {
          const group = tasks.filter((task) => task.state === state)
          if (group.length === 0) return null
          const title =
            state === 'NEEDS_APPROVAL'
              ? 'Waiting on your approval'
              : state === 'BLOCKED'
                ? 'Blocked'
                : 'Failed'
          return (
            <section key={state} className="space-y-3">
              <h2
                className={cn(
                  'text-xs font-semibold uppercase tracking-widest',
                  STATE_TONE[state],
                )}
              >
                {title}
              </h2>
              <div className="space-y-2">
                {group.map((task) => (
                  <AttentionCard
                    key={task.id}
                    task={task}
                    nextStates={transitionsQuery.data?.[task.state] ?? null}
                    pending={transition.isPending && transition.variables?.id === task.id}
                    error={transitionErrors[task.id] ?? null}
                    onTransition={(next) => transition.mutate({ id: task.id, state: next })}
                  />
                ))}
              </div>
            </section>
          )
        })
      )}
    </div>
  )
}
