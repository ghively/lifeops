/**
 * Actions — the outbox (BUILD_SPEC sections 60-63).
 *
 * This is where an approval turns into something that actually happened.
 * Approving a card on the Approvals screen only clears an action to go out;
 * a human still runs it from here (Execute), and then independently confirms
 * it against the outside world (Verify) — section 6: the provider accepting
 * a request is not evidence the thing happened.
 *
 * LifeOps Core owns every rule (which statuses may execute, what verification
 * checks); this screen only shows the outbox and submits the two verbs.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Loader2, Send } from 'lucide-react'

import { QueryError } from '@/components/QueryError'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import {
  ACTION_TYPE_LABELS,
  actionsApi,
  errorMessage,
  type ActionStatus,
  type LifeOpsAction,
} from '@/services/lifeops'

/** Everything except terminal clutter; VERIFIED stays visible as the proof. */
const SHOWN_STATUSES: ActionStatus[] = [
  'needs_approval',
  'approved',
  'executing',
  'executed',
  'verified',
  'failed',
]

const STATUS_BADGE: Record<ActionStatus, { label: string; className: string }> = {
  prepared: { label: 'Prepared', className: 'text-muted-foreground' },
  needs_approval: { label: 'Awaiting approval', className: 'text-amber-600' },
  approved: { label: 'Approved — ready to run', className: 'text-sky-600' },
  executing: { label: 'Executing', className: 'text-sky-600' },
  executed: { label: 'Executed — needs verification', className: 'text-amber-600' },
  verified: { label: 'Verified', className: 'text-emerald-600' },
  failed: { label: 'Failed', className: 'text-red-600' },
  cancelled: { label: 'Cancelled', className: 'text-muted-foreground line-through' },
}

function when(iso: string | null): string {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function ActionCard({
  action,
  onExecute,
  onVerify,
  busy,
}: {
  action: LifeOpsAction
  onExecute: () => void
  onVerify: () => void
  busy: boolean
}) {
  const badge = STATUS_BADGE[action.status]
  return (
    <div className="rounded-lg border border-border/60 bg-card px-4 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="font-medium">
          {ACTION_TYPE_LABELS[action.type] ?? action.type}
        </span>
        <span className={cn('text-xs font-medium', badge?.className)}>
          {badge?.label ?? action.status}
        </span>
      </div>
      <dl className="mt-2 space-y-1 text-xs text-muted-foreground">
        <div>Prepared {when(action.created_at)}</div>
        {action.last_attempt_at ? (
          <div>
            Last attempt {when(action.last_attempt_at)} · attempt{' '}
            {action.attempt_count}
          </div>
        ) : null}
        {action.external_reference ? (
          <div>External reference: {action.external_reference}</div>
        ) : null}
        {action.failure_reason ? (
          <div className="text-red-600">{action.failure_reason}</div>
        ) : null}
      </dl>
      <div className="mt-3 flex gap-2">
        {action.status === 'approved' ? (
          <Button size="sm" disabled={busy} onClick={onExecute}>
            Execute
          </Button>
        ) : null}
        {action.status === 'executed' ? (
          <Button size="sm" variant="outline" disabled={busy} onClick={onVerify}>
            Verify externally
          </Button>
        ) : null}
      </div>
    </div>
  )
}

export function ActionsPage() {
  const queryClient = useQueryClient()

  const actionsQuery = useQuery({
    queryKey: ['lifeops', 'actions', SHOWN_STATUSES],
    queryFn: () => actionsApi.list({ status: SHOWN_STATUSES, limit: 100 }),
    refetchInterval: 15_000,
  })

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ['lifeops', 'actions'] })

  const execute = useMutation({
    mutationFn: (id: string) => actionsApi.execute(id),
    onSuccess: invalidate,
    onError: invalidate,
  })
  const verify = useMutation({
    mutationFn: (id: string) => actionsApi.verifyExternally(id),
    onSuccess: invalidate,
    onError: invalidate,
  })

  if (actionsQuery.isError) {
    return (
      <div className="p-8">
        <QueryError
          message={errorMessage(actionsQuery.error)}
          onRetry={() => void actionsQuery.refetch()}
        />
      </div>
    )
  }

  const actions = actionsQuery.data?.actions ?? []
  const mutationError = execute.isError
    ? errorMessage(execute.error)
    : verify.isError
      ? errorMessage(verify.error)
      : null

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-8">
      <header>
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <Send className="h-5 w-5" />
          Actions
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          The outbox. An approved action runs from here, and an executed one is
          independently verified before LifeOps believes it happened.
        </p>
      </header>

      {mutationError ? (
        <p
          role="alert"
          className="rounded-lg border border-red-300/60 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800/60 dark:bg-red-950/40 dark:text-red-300"
        >
          {mutationError}
        </p>
      ) : null}

      {actionsQuery.isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading…
        </div>
      ) : actions.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border/60 px-4 py-8 text-center text-sm text-muted-foreground">
          The outbox is empty — nothing is waiting to run or be verified.
        </p>
      ) : (
        <div className="space-y-3">
          {actions.map((action) => (
            <ActionCard
              key={action.id}
              action={action}
              busy={
                (execute.isPending && execute.variables === action.id) ||
                (verify.isPending && verify.variables === action.id)
              }
              onExecute={() => execute.mutate(action.id)}
              onVerify={() => verify.mutate(action.id)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
