/**
 * Waiting — work blocked on another person, organisation, service, or future
 * event (BUILD_SPEC section 13).
 *
 * Each item shows subject, task, waiting on, waiting since, expected
 * response, next follow-up, follow-up count, and escalation state — the
 * exact list section 13 asks for. LifeOps Core owns every rule that decides
 * these values (the follow-up backoff, when an item escalates); this screen
 * only displays them and submits "log a follow-up" / "mark resolved".
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, Hourglass, Loader2 } from 'lucide-react'

import { QueryError } from '@/components/QueryError'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import {
  errorMessage,
  tasksApi,
  waitingApi,
  type WaitingItem,
  type WaitingStatus,
} from '@/services/lifeops'

const ACTIVE_STATUSES: WaitingStatus[] = ['waiting', 'escalated']

/** Compact elapsed time, in the style of the spec's examples ("2h", "2 days"). */
function since(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime()
  if (Number.isNaN(ms) || ms < 0) return ''
  const minutes = Math.floor(ms / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  if (hours < 48) return `${hours}h`
  return `${Math.floor(hours / 24)} days`
}

/** Compact time-until, for a future instant like the next follow-up. */
function until(iso: string): string {
  const ms = new Date(iso).getTime() - Date.now()
  if (Number.isNaN(ms)) return ''
  if (ms <= 0) return 'due now'
  const minutes = Math.floor(ms / 60_000)
  if (minutes < 60) return `in ${minutes}m`
  const hours = Math.floor(minutes / 60)
  if (hours < 48) return hours < 24 ? `in ${hours}h` : 'tomorrow'
  return `in ${Math.floor(hours / 24)} days`
}

function formatDate(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

const STATUS_BADGE: Record<WaitingStatus, { label: string; className: string }> = {
  waiting: { label: 'Waiting', className: 'text-amber-600' },
  escalated: { label: 'Escalated — needs you', className: 'text-red-600' },
  resolved: { label: 'Resolved', className: 'text-emerald-600' },
  cancelled: { label: 'Cancelled', className: 'text-muted-foreground' },
}

function WaitingCard({
  item,
  onFollowUp,
  onResolve,
  followUpPending,
  resolvePending,
}: {
  item: WaitingItem
  onFollowUp: () => void
  onResolve: () => void
  followUpPending: boolean
  resolvePending: boolean
}) {
  const taskQuery = useQuery({
    queryKey: ['lifeops', 'tasks', item.task_id],
    queryFn: () => tasksApi.get(item.task_id),
    staleTime: 60_000,
  })

  const badge = STATUS_BADGE[item.status]
  const active = item.status === 'waiting' || item.status === 'escalated'

  return (
    <div
      className={cn(
        'rounded-lg border border-l-4 border-border/60 bg-card px-4 py-3',
        item.status === 'escalated' ? 'border-l-red-500' : 'border-l-amber-500',
      )}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <p className="font-medium">{item.subject}</p>
          <p className="mt-1 text-sm text-muted-foreground">
            {taskQuery.data?.title ?? item.task_id}
          </p>
          {item.waiting_on_entity_id && (
            <p className="mt-1 text-sm text-muted-foreground">
              Waiting on <span className="font-mono">{item.waiting_on_entity_id}</span>
            </p>
          )}

          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            {since(item.waiting_since) && <span>waiting {since(item.waiting_since)}</span>}
            <span>
              expected{' '}
              {item.expected_by ? formatDate(item.expected_by) : 'response time not set'}
            </span>
            {item.status !== 'resolved' && item.status !== 'cancelled' && (
              <span>
                next follow-up{' '}
                {item.next_action_at ? until(item.next_action_at) : 'none scheduled'}
              </span>
            )}
            <span>
              {item.followup_count} of {item.max_followups} follow-ups
            </span>
          </div>

          <p className={cn('mt-2 flex items-center gap-1 text-xs font-medium', badge.className)}>
            {item.status === 'escalated' && <AlertTriangle className="h-3.5 w-3.5" />}
            {badge.label}
          </p>
        </div>

        {active && (
          <div className="flex shrink-0 flex-col gap-1.5">
            <Button
              variant="outline"
              size="sm"
              disabled={followUpPending}
              onClick={onFollowUp}
            >
              {followUpPending && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
              Log follow-up
            </Button>
            <Button variant="ghost" size="sm" disabled={resolvePending} onClick={onResolve}>
              <CheckCircle2 className="mr-1 h-3.5 w-3.5" />
              Mark resolved
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}

export function WaitingPage() {
  const queryClient = useQueryClient()

  const waitingQuery = useQuery({
    queryKey: ['lifeops', 'waiting', ACTIVE_STATUSES],
    queryFn: () => waitingApi.list({ status: ACTIVE_STATUSES, limit: 200 }),
    refetchInterval: 30_000,
  })

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ['lifeops', 'waiting'] })

  const followUp = useMutation({
    mutationFn: (id: string) => waitingApi.followUp(id),
    onSuccess: invalidate,
    onError: invalidate,
  })

  const resolve = useMutation({
    mutationFn: (id: string) => waitingApi.resolve(id),
    onSuccess: invalidate,
    onError: invalidate,
  })

  if (waitingQuery.isError) {
    return (
      <div className="p-8">
        <QueryError
          message={errorMessage(waitingQuery.error)}
          onRetry={() => void waitingQuery.refetch()}
        />
      </div>
    )
  }

  const items = waitingQuery.data?.items ?? []

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-8">
      <header>
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <Hourglass className="h-5 w-5" />
          Waiting
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Work blocked on another person, organisation, service, or future event.
        </p>
      </header>

      {followUp.isError || resolve.isError ? (
        <p
          role="alert"
          className="rounded-lg border border-red-300/60 bg-red-50 px-4 py-2 text-sm text-red-700 dark:border-red-800/60 dark:bg-red-950/40 dark:text-red-300"
        >
          {followUp.isError
            ? `The follow-up was not recorded: ${errorMessage(followUp.error)}`
            : `The item was not resolved: ${errorMessage(resolve.error)}`}
        </p>
      ) : null}

      {waitingQuery.isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading…
        </div>
      ) : items.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border/60 px-4 py-8 text-center text-sm text-muted-foreground">
          Nothing is waiting on the outside world.
        </p>
      ) : (
        <div className="space-y-2">
          {items.map((item) => (
            <WaitingCard
              key={item.id}
              item={item}
              onFollowUp={() => followUp.mutate(item.id)}
              onResolve={() => resolve.mutate(item.id)}
              followUpPending={followUp.isPending && followUp.variables === item.id}
              resolvePending={resolve.isPending && resolve.variables === item.id}
            />
          ))}
        </div>
      )}
    </div>
  )
}
