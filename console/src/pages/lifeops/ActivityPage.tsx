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
 *
 * Section 21 asks for "human-readable audit trail first" with technical
 * detail (trace ID, task ID, client ID, tool, risk class, duration, action
 * ID, verification evidence) behind an expand action. `narrateAudit`/
 * `narrateActivity` turn the intent/operation identifier LifeOps recorded
 * (`task.create`, `decide_approval`, ...) into a sentence; an identifier not
 * in the lookup still renders — humanised from its own name — rather than
 * disappearing, since a narrative screen that goes blank on an unmapped
 * intent is worse than one that shows something plain.
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Activity, ChevronDown, ChevronRight, Loader2 } from 'lucide-react'

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

const CLIENT_LABELS: Record<string, string> = {
  'hermes-personal': 'Hermes',
  'interactive-mcp': 'The interactive session',
  'claude-code': 'Claude Code',
  'lifeops-console': 'The Console',
  'lifeops-worker': 'The due-work worker',
}

function clientLabel(clientId: string | null | undefined): string {
  if (!clientId) return 'LifeOps'
  return CLIENT_LABELS[clientId] ?? clientId
}

/** `task.create` -> "Task create", `record_bill` -> "Record bill" — a plain
 * fallback for any identifier not in the lookup below. */
function humanizeIdentifier(id: string): string {
  const words = id.replace(/[._]/g, ' ').trim()
  return words.charAt(0).toUpperCase() + words.slice(1)
}

/** Durable audit log intents (core.py's `self.audit(..., intent=...)` calls)
 * — one sentence-builder per intent, given the client and the record. */
const AUDIT_NARRATIVES: Record<string, (record: AuditRecord) => string> = {
  add_shopping_items: (r) => `${clientLabel(r.client)} added items to a shopping list.`,
  apply_substitution: (r) => `${clientLabel(r.client)} substituted an item in a shopping list.`,
  approve_payee: (r) => `${clientLabel(r.client)} approved a payee for payments.`,
  cancel_service_request: (r) => `${clientLabel(r.client)} cancelled a service request.`,
  commit_action: (r) => `${clientLabel(r.client)} committed an approved action.`,
  complete_service_request: (r) => `${clientLabel(r.client)} completed a service request.`,
  confirm_service_booking: (r) => `${clientLabel(r.client)} confirmed a service booking.`,
  create_appointment_hold: (r) => `${clientLabel(r.client)} held a calendar appointment.`,
  create_document: (r) => `${clientLabel(r.client)} recorded a document reference.`,
  create_service_request: (r) => `${clientLabel(r.client)} opened a service request.`,
  create_shopping_list: (r) => `${clientLabel(r.client)} started a shopping list.`,
  create_waiting_item: (r) =>
    `${clientLabel(r.client)} recorded that a task is waiting on someone else.`,
  decide_approval: (r) => `${clientLabel(r.client)} decided a pending approval: ${r.result}.`,
  delete_workflow_template: (r) => `${clientLabel(r.client)} deleted a workflow template.`,
  prepare_action: (r) => `${clientLabel(r.client)} prepared an action for approval.`,
  promote_memory: (r) => `${clientLabel(r.client)} promoted a memory to a preference.`,
  record_action_result: (r) => `An action finished: ${r.result}.`,
  record_bill: (r) => `${clientLabel(r.client)} recorded a bill.`,
  record_followup: (r) => `${clientLabel(r.client)} logged a follow-up.`,
  record_knowledge: (r) => `${clientLabel(r.client)} recorded a piece of knowledge.`,
  record_payee: (r) => `${clientLabel(r.client)} recorded a payee.`,
  request_code_change: (r) => `${clientLabel(r.client)} filed a code change request.`,
  resolve_waiting_item: (r) => `${clientLabel(r.client)} resolved a waiting item.`,
  save_workflow_template: (r) => `${clientLabel(r.client)} saved a workflow template.`,
  settle_bill: (r) => `${clientLabel(r.client)} marked a bill as paid.`,
  verify_action: (r) => `${clientLabel(r.client)} verified an executed action.`,
}

/** The ephemeral feed's `operation(...)` identifiers — a different, dotted
 * vocabulary from the audit log's, since the two are genuinely separate
 * instrumentation points. */
const ACTIVITY_NARRATIVES: Record<string, (entry: ActivityEntry) => string> = {
  'bill.record': (e) => `${clientLabel(e.client_id)} recorded a bill.`,
  'calendar.read': (e) => `${clientLabel(e.client_id)} read the calendar.`,
  'memory.invalidate': (e) => `${clientLabel(e.client_id)} invalidated a memory.`,
  'memory.recall': (e) => `${clientLabel(e.client_id)} searched memory.`,
  'person.create': (e) => `${clientLabel(e.client_id)} added a person.`,
  'person.get': (e) => `${clientLabel(e.client_id)} looked up a person.`,
  'search.query': (e) => `${clientLabel(e.client_id)} ran a search.`,
  'task.create': (e) => `${clientLabel(e.client_id)} created a task.`,
  'task.list': (e) => `${clientLabel(e.client_id)} listed tasks.`,
  'waiting.create': (e) => `${clientLabel(e.client_id)} recorded a waiting item.`,
  'waiting.resolve': (e) => `${clientLabel(e.client_id)} resolved a waiting item.`,
  'world.entity_detail': (e) => `${clientLabel(e.client_id)} inspected a world entity.`,
  'world.entity_history': (e) => `${clientLabel(e.client_id)} viewed an entity's history.`,
  'world.graph': (e) => `${clientLabel(e.client_id)} viewed the world graph.`,
}

function narrateAudit(record: AuditRecord): string {
  const key = record.intent ?? ''
  const builder = AUDIT_NARRATIVES[key]
  if (builder) return builder(record)
  return key
    ? `${clientLabel(record.client)} — ${humanizeIdentifier(key)} (${record.result}).`
    : `${clientLabel(record.client)} — ${record.result}.`
}

function narrateActivity(entry: ActivityEntry): string {
  const builder = ACTIVITY_NARRATIVES[entry.operation]
  if (builder) return builder(entry)
  return `${clientLabel(entry.client_id)} — ${humanizeIdentifier(entry.operation)} (${entry.result}).`
}

function DetailRow({ label, value }: { label: string; value: string | number | null }) {
  if (value === null || value === '') return null
  return (
    <div className="flex items-baseline justify-between gap-3 text-xs">
      <dt className="shrink-0 text-muted-foreground">{label}</dt>
      <dd className="truncate text-right font-mono">{value}</dd>
    </div>
  )
}

function AuditRow({ record }: { record: AuditRecord }) {
  const [expanded, setExpanded] = useState(false)
  const failed =
    record.result.includes('fail') ||
    record.result.includes('denied') ||
    record.result.includes('error')
  return (
    <div className="rounded-lg border border-border/60 px-4 py-3">
      <button
        type="button"
        onClick={() => setExpanded((current) => !current)}
        className="flex w-full items-start justify-between gap-4 text-left"
        aria-expanded={expanded}
        aria-label={`Show technical detail for: ${narrateAudit(record)}`}
      >
        <p className="flex min-w-0 flex-1 items-start gap-1.5">
          {expanded ? (
            <ChevronDown className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          )}
          <span className={cn('text-sm', failed && 'text-red-600')}>{narrateAudit(record)}</span>
        </p>
        <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
          {formatTime(record.timestamp)}
        </span>
      </button>
      {expanded && (
        <dl className="mt-3 space-y-1 border-t border-border/40 pt-2">
          <DetailRow label="Trace ID" value={record.trace_id} />
          <DetailRow label="Client ID" value={record.client} />
          <DetailRow label="Tool" value={record.tool} />
          <DetailRow label="Risk class" value={record.risk} />
          <DetailRow label="Action ID" value={record.action} />
          <DetailRow label="Target" value={record.target} />
          <DetailRow label="Verification evidence" value={record.verification} />
          <DetailRow label="Intent" value={record.intent} />
          <DetailRow label="Result" value={record.result} />
        </dl>
      )}
    </div>
  )
}

function ActivityRow({ entry }: { entry: ActivityEntry }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div className="rounded-lg border border-border/60 px-4 py-3">
      <button
        type="button"
        onClick={() => setExpanded((current) => !current)}
        className="flex w-full items-start justify-between gap-4 text-left"
        aria-expanded={expanded}
        aria-label={`Show technical detail for: ${narrateActivity(entry)}`}
      >
        <p className="flex min-w-0 flex-1 items-start gap-1.5">
          {expanded ? (
            <ChevronDown className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          )}
          <span className={cn('text-sm', entry.result !== 'ok' && 'text-red-600')}>
            {narrateActivity(entry)}
          </span>
        </p>
        <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
          {formatTime(entry.ts)}
        </span>
      </button>
      {expanded && (
        <dl className="mt-3 space-y-1 border-t border-border/40 pt-2">
          <DetailRow label="Client ID" value={entry.client_id ?? null} />
          <DetailRow label="Task ID" value={entry.task_id ?? null} />
          <DetailRow label="Person ID" value={entry.person_id ?? null} />
          <DetailRow label="Subject ID" value={entry.subject_id ?? null} />
          <DetailRow label="Key" value={entry.key ?? null} />
          <DetailRow
            label="Duration"
            value={entry.duration_ms !== null ? `${entry.duration_ms.toFixed(0)} ms` : null}
          />
          <DetailRow label="Operation" value={entry.operation} />
          <DetailRow label="Result" value={entry.result} />
        </dl>
      )}
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
