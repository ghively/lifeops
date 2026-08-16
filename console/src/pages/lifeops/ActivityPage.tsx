/**
 * Activity — a human-readable feed of what the assistant did, and why
 * (BUILD_SPEC section 21).
 *
 * Phase 1 serves recent entries from an in-memory buffer in LifeOps Core:
 * the feed is ephemeral and disappears on restart. The durable, queryable
 * audit trail (BUILD_SPEC section 62) arrives in Phase 4, and the screen
 * labels itself accordingly rather than implying a history it does not have.
 */

import { useQuery } from '@tanstack/react-query'
import { Activity, Loader2 } from 'lucide-react'

import { QueryError } from '@/components/QueryError'
import { cn } from '@/lib/utils'
import { errorMessage, systemApi, type ActivityEntry } from '@/services/lifeops'

function formatTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
  })
}

function ActivityRow({ entry }: { entry: ActivityEntry }) {
  const detail = [entry.task_id, entry.person_id, entry.subject_id, entry.key].find(Boolean)
  return (
    <div className="rounded-lg border border-border/60 px-4 py-3">
      <div className="flex items-baseline justify-between gap-4">
        <p className="min-w-0 flex-1">
          <span className="font-mono text-sm">{entry.operation}</span>{' '}
          <span
            className={cn(
              'text-xs',
              entry.result === 'ok' ? 'text-muted-foreground' : 'text-red-600',
            )}
          >
            {entry.result}
          </span>
        </p>
        <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
          {formatTime(entry.ts)}
        </span>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        {entry.client_id && <span className="font-medium">{entry.client_id}</span>}
        {detail && <span className="font-mono">{detail}</span>}
        {entry.duration_ms !== null && (
          <span className="tabular-nums">{entry.duration_ms.toFixed(0)} ms</span>
        )}
      </div>
    </div>
  )
}

export function ActivityPage() {
  const activityQuery = useQuery({
    queryKey: ['lifeops', 'activity'],
    queryFn: systemApi.getActivity,
    refetchInterval: 15_000,
  })

  if (activityQuery.isError) {
    return (
      <div className="p-8">
        <QueryError
          message={errorMessage(activityQuery.error)}
          onRetry={() => void activityQuery.refetch()}
        />
      </div>
    )
  }

  // Newest first, regardless of the order the buffer happened to return.
  const entries = [...(activityQuery.data ?? [])].sort(
    (a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime(),
  )

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-8">
      <header>
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <Activity className="h-5 w-5" />
          Activity
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          What the assistant has been doing, newest first.
        </p>
      </header>

      {activityQuery.isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading…
        </div>
      ) : entries.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border/60 px-4 py-8 text-center text-sm text-muted-foreground">
          No recent activity.
        </p>
      ) : (
        <div className="space-y-2">
          {entries.map((entry, index) => (
            <ActivityRow key={`${entry.ts}-${index}`} entry={entry} />
          ))}
        </div>
      )}

      <footer className="rounded-lg border border-dashed border-border/60 px-4 py-4 text-sm text-muted-foreground">
        <p className="font-medium text-foreground">Ephemeral recent activity</p>
        <p className="mt-1">
          This feed is held in memory and resets when LifeOps Core restarts.
          The durable audit trail arrives in Phase 4.
        </p>
      </footer>
    </div>
  )
}
