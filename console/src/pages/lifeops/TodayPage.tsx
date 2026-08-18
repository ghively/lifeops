/**
 * Today — the default LifeOps Console screen (BUILD_SPEC section 11).
 *
 * Shows what needs attention, what is in progress, and what recently
 * completed. Phase 0 has no approvals, waiting items, or calendar, so those
 * sections state plainly that they arrive later rather than rendering an empty
 * box that reads like a bug.
 */

import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { AlertCircle, CheckCircle2, Clock, Loader2 } from 'lucide-react'

import { QueryError } from '@/components/QueryError'
import {
  TASK_STATE_LABELS,
  errorMessage,
  peopleApi,
  tasksApi,
  type Task,
} from '@/services/lifeops'
import { cn } from '@/lib/utils'

const ATTENTION_STATES = new Set(['NEEDS_APPROVAL', 'BLOCKED', 'FAILED'])
const ACTIVE_STATES = new Set([
  'EXECUTING',
  'WAITING_EXTERNAL',
  'VERIFYING',
  'READY',
])

function formatDay(): string {
  return new Date().toLocaleDateString(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  })
}

function TaskRow({ task }: { task: Task }) {
  return (
    <Link
      to="/tasks"
      className="flex items-start justify-between gap-4 rounded-lg border border-border/60 px-4 py-3 transition-colors hover:bg-muted/50"
    >
      <div className="min-w-0">
        <p className="truncate font-medium">{task.title}</p>
        <p className="mt-0.5 text-sm text-muted-foreground">
          {TASK_STATE_LABELS[task.state]}
          {task.current_action ? ` · ${task.current_action}` : ''}
          {task.verification_required ? ' · verification required' : ''}
        </p>
      </div>
      <span className="shrink-0 text-xs uppercase tracking-wide text-muted-foreground">
        {task.priority}
      </span>
    </Link>
  )
}

function Section({
  title,
  icon: Icon,
  tasks,
  empty,
}: {
  title: string
  icon: typeof AlertCircle
  tasks: Task[]
  empty: string
}) {
  return (
    <section className="space-y-3">
      <h2 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
        <Icon className="h-3.5 w-3.5" />
        {title}
      </h2>
      {tasks.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border/60 px-4 py-6 text-sm text-muted-foreground">
          {empty}
        </p>
      ) : (
        <div className="space-y-2">
          {tasks.map((task) => (
            <TaskRow key={task.id} task={task} />
          ))}
        </div>
      )}
    </section>
  )
}

export function TodayPage() {
  const tasksQuery = useQuery({
    queryKey: ['lifeops', 'tasks'],
    queryFn: () => tasksApi.list({ limit: 200 }),
    refetchInterval: 30_000,
  })
  const meQuery = useQuery({
    queryKey: ['lifeops', 'me'],
    queryFn: peopleApi.me,
    retry: false,
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
  const needsAttention = tasks.filter((t) => ATTENTION_STATES.has(t.state))
  const inProgress = tasks.filter((t) => ACTIVE_STATES.has(t.state))
  const captured = tasks.filter(
    (t) => t.state === 'CAPTURED' || t.state === 'PLANNED',
  )
  const completed = tasks.filter((t) => t.state === 'COMPLETED').slice(0, 5)

  return (
    <div className="mx-auto max-w-3xl space-y-10 p-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Today</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {formatDay()}
          {meQuery.data ? ` · ${meQuery.data.display_name}` : ''}
        </p>
      </header>

      {tasksQuery.isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading from LifeOps Core…
        </div>
      ) : (
        <>
          <Section
            title="Needs you"
            icon={AlertCircle}
            tasks={needsAttention}
            empty="Nothing is waiting on you."
          />
          <Section
            title="In progress"
            icon={Loader2}
            tasks={inProgress}
            empty="Nothing is in flight."
          />
          <Section
            title="Captured"
            icon={Clock}
            tasks={captured}
            empty="No captured tasks."
          />
          <Section
            title="Recently completed"
            icon={CheckCircle2}
            tasks={completed}
            empty="Nothing completed yet."
          />
        </>
      )}

      <footer
        className={cn(
          'rounded-lg border border-dashed border-border/60 px-4 py-4',
          'text-sm text-muted-foreground',
        )}
      >
        <p className="font-medium text-foreground">Tasks only, for now</p>
        <p className="mt-1">
          Today reflects LifeOps task state. Pending approvals, waiting
          items, and calendar events exist in the sidebar screens but are
          not folded into this view yet (BUILD_SPEC section 11 asks for
          them here — recorded as an open gap in docs/audits/).
        </p>
      </footer>
    </div>
  )
}
