/**
 * Activity — what the assistant did, and why (BUILD_SPEC sections 21, 62).
 *
 * Two sources, shown together because each covers what the other cannot:
 *
 *  - The durable audit log (section 62), read from NornicDB. It survives
 *    restarts and records every semantic operation from every process —
 *    including everything Hermes does over MCP, which this HTTP process
 *    never sees live.
 *  - This process's in-memory feed: finer-grained (durations, trace IDs)
 *    but ephemeral and blind to the MCP process.
 */

import { useQuery } from '@tanstack/react-query'
import { Activity, Loader2 } from 'lucide-react'

import { QueryError } from '@/components/QueryError'
import { cn } from '@/lib/utils'
import {
  auditApi,
  errorMessage,
  systemApi,
  type ActivityEntry,
  type AuditRecord,
} from '@/services/lifeops'

function formatTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function AuditRow({ record }: { record: AuditRecord }) {
  const failed =
    record.result.includes('fail') ||
    record.result.includes('denied') ||
    record.result.includes('error')
  const detail = [record.tool, record.target, record.action].find(Boolean)
  return (
    <div className="rounded-lg border border-border/60 px-4 py-3">
      <div className="flex items-baseline justify-between gap-4">
        <p className="min-w-0 flex-1">
          <span className="font-mono text-sm">{record.intent ?? record.result}</span>{' '}
          <span
            className={cn('text-xs', failed ? 'text-red-600' : 'text-muted-foreground')}
          >
            {record.result}
          </span>
        </p>
        <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
          {formatTime(record.timestamp)}
        </span>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        <span className="font-medium">{record.client}</span>
        {record.risk && <span>risk {record.risk}</span>}
        {detail && <span className="font-mono">{detail}</span>}
        {record.verification && <span>verification: {record.verification}</span>}
        {record.trace_id && <span className="font-mono">{record.trace_id}</span>}
      </div>
    </div>
  )
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
  const auditQuery = useQuery({
    queryKey: ['lifeops', 'audit'],
    queryFn: () => auditApi.read({ limit: 100 }),
    refetchInterval: 30_000,
  })
  const activityQuery = useQuery({
    queryKey: ['lifeops', 'activity'],
    queryFn: systemApi.getActivity,
    refetchInterval: 15_000,
  })

  if (auditQuery.isError && activityQuery.isError) {
    return (
      <div className="p-8">
        <QueryError
          message={errorMessage(auditQuery.error)}
          onRetry={() => {
            void auditQuery.refetch()
            void activityQuery.refetch()
          }}
        />
      </div>
    )
  }

  const records = auditQuery.data?.records ?? []
  // Newest first, regardless of the order the buffer happened to return.
  const entries = [...(activityQuery.data ?? [])].sort(
    (a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime(),
  )

  return (
    <div className="mx-auto max-w-3xl space-y-8 p-8">
      <header>
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <Activity className="h-5 w-5" />
          Activity
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          What the assistant has been doing, newest first.
        </p>
      </header>

      <section className="space-y-2">
        <h2 className="text-sm font-semibold">Audit log</h2>
        <p className="text-xs text-muted-foreground">
          Durable, from every surface — including everything Hermes does over
          MCP. Survives restarts.
        </p>
        {auditQuery.isLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading…
          </div>
        ) : records.length === 0 ? (
          <p className="rounded-lg border border-dashed border-border/60 px-4 py-6 text-center text-sm text-muted-foreground">
            {auditQuery.isError
              ? `The audit log could not be read: ${errorMessage(auditQuery.error)}`
              : 'Nothing recorded yet.'}
          </p>
        ) : (
          <div className="space-y-2">
            {records.map((record) => (
              <AuditRow key={record.id} record={record} />
            ))}
          </div>
        )}
      </section>

      <section className="space-y-2">
        <h2 className="text-sm font-semibold">This process, live</h2>
        <p className="text-xs text-muted-foreground">
          Finer-grained (durations, traces) but in-memory only: it resets on
          restart and does not see the separately running MCP server.
        </p>
        {activityQuery.isLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading…
          </div>
        ) : entries.length === 0 ? (
          <p className="rounded-lg border border-dashed border-border/60 px-4 py-6 text-center text-sm text-muted-foreground">
            No recent activity in this process.
          </p>
        ) : (
          <div className="space-y-2">
            {entries.map((entry, index) => (
              <ActivityRow key={`${entry.ts}-${index}`} entry={entry} />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
