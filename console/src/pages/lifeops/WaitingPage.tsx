/**
 * Waiting — work blocked on another person, organisation, service, or future
 * event (BUILD_SPEC section 13).
 *
 * Phase 1 shows tasks in WAITING_EXTERNAL: the subject, what LifeOps is
 * waiting on, and how long it has been waiting. Full WaitingItems — expected
 * response times, follow-ups, escalation — arrive in Phase 4, so this screen
 * says so rather than rendering empty boxes that read like a bug.
 */

import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Hourglass, Loader2 } from 'lucide-react'

import { QueryError } from '@/components/QueryError'
import { errorMessage, tasksApi, type Task } from '@/services/lifeops'

/** Compact age, in the style of the spec's examples ("2h", "2 days"). */
function waitingSince(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime()
  if (Number.isNaN(ms) || ms < 0) return ''
  const minutes = Math.floor(ms / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  if (hours < 48) return `${hours}h`
  return `${Math.floor(hours / 24)}d`
}

function WaitingRow({ task }: { task: Task }) {
  // updated_at is when the task last changed — for a waiting task, when it
  // entered (or last moved within) the waiting state.
  const since = waitingSince(task.updated_at)

  return (
    <Link
      to="/tasks"
      className="block rounded-lg border border-border/60 px-4 py-3 transition-colors hover:bg-muted/50"
    >
      <p className="font-medium">{task.title}</p>
      <p className="mt-1 text-sm text-amber-500">
        {task.current_action
          ? `Waiting: ${task.current_action}`
          : 'Waiting on an external response'}
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        {since && <span>for {since}</span>}
        <span>{task.priority}</span>
        {task.created_by_client && <span>via {task.created_by_client}</span>}
      </div>
    </Link>
  )
}

export function WaitingPage() {
  const tasksQuery = useQuery({
    queryKey: ['lifeops', 'tasks', 'waiting'],
    queryFn: () => tasksApi.list({ state: ['WAITING_EXTERNAL'], limit: 200 }),
    refetchInterval: 30_000,
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
          <Hourglass className="h-5 w-5" />
          Waiting
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Work blocked on another person, organisation, or future event.
        </p>
      </header>

      {tasksQuery.isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading…
        </div>
      ) : tasks.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border/60 px-4 py-8 text-center text-sm text-muted-foreground">
          Nothing is waiting on the outside world.
        </p>
      ) : (
        <div className="space-y-2">
          {tasks.map((task) => (
            <WaitingRow key={task.id} task={task} />
          ))}
        </div>
      )}

      <footer className="rounded-lg border border-dashed border-border/60 px-4 py-4 text-sm text-muted-foreground">
        <p className="font-medium text-foreground">Phase 1</p>
        <p className="mt-1">
          Full waiting items — expected response times, follow-ups, and
          escalation — arrive in Phase 4. This screen currently shows tasks in
          the waiting state.
        </p>
      </footer>
    </div>
  )
}
