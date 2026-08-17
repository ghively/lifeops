/**
 * Approvals — one human decision per exact action (BUILD_SPEC section 58).
 *
 * LifeOps Core decides whether an action needs approval and exactly what an
 * approval authorises (the payload hash binding of section 57); this screen
 * only renders that decision and submits Approve/Decline. It never computes
 * whether approval is required.
 *
 * The mockup in section 58 shows, for one approval: what will happen, what
 * Hermes may do, what it may not, and the two buttons. "What will happen" is
 * the exact payload the server attached to the approval (`action_payload`) —
 * the same payload the payload-hash binding is computed from, so nothing
 * shown here can drift from what gets committed. "Hermes may not" is stated
 * generically rather than per action type: every approval in this system
 * authorises exactly one exact request, and nothing else, by construction
 * (section 57's "material change invalidates approval").
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Loader2, ShieldCheck, X } from 'lucide-react'

import { QueryError } from '@/components/QueryError'
import { Button } from '@/components/ui/button'
import {
  ACTION_TYPE_LABELS,
  approvalsApi,
  errorMessage,
  type ActionType,
  type Approval,
} from '@/services/lifeops'

function actionTypeLabel(type: string): string {
  return ACTION_TYPE_LABELS[type as ActionType] ?? type
}

function formatPayloadValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function ApprovalCard({
  approval,
  onDecide,
  pendingDecision,
}: {
  approval: Approval
  onDecide: (approved: boolean) => void
  pendingDecision: boolean
}) {
  const payloadEntries = Object.entries(approval.action_payload)

  return (
    <div className="rounded-lg border border-border/60 bg-card p-5">
      <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
        {approval.target_entity_id ?? actionTypeLabel(approval.action_type)}
      </p>

      {payloadEntries.length > 0 && (
        <dl className="mt-3 space-y-1">
          {payloadEntries.map(([key, value]) => (
            <div key={key} className="flex items-baseline gap-2 text-sm">
              <dt className="text-muted-foreground">{key.replace(/_/g, ' ')}</dt>
              <dd className="font-medium">{formatPayloadValue(value)}</dd>
            </div>
          ))}
        </dl>
      )}

      {approval.amount && (
        <p className="mt-2 text-sm">
          <span className="text-muted-foreground">Amount</span>{' '}
          <span className="font-medium">{approval.amount}</span>
        </p>
      )}

      {approval.target_entity_id && (
        <p className="mt-2 text-sm">
          <span className="text-muted-foreground">For</span>{' '}
          <span className="font-mono">{approval.target_entity_id}</span>
        </p>
      )}

      <div className="mt-4 space-y-1 border-t border-border/60 pt-3 text-sm">
        <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
          Hermes may
        </p>
        <p className="flex items-center gap-1.5 text-emerald-600">
          <Check className="h-3.5 w-3.5" />
          {actionTypeLabel(approval.action_type)}
        </p>
        <p className="flex items-center gap-1.5 text-red-600">
          <X className="h-3.5 w-3.5" />
          Anything other than this exact request
        </p>
      </div>

      <div className="mt-4 flex justify-between gap-3">
        <Button
          variant="outline"
          disabled={pendingDecision}
          onClick={() => onDecide(false)}
        >
          Decline
        </Button>
        <Button disabled={pendingDecision} onClick={() => onDecide(true)}>
          {pendingDecision && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
          Approve
        </Button>
      </div>
    </div>
  )
}

export function ApprovalsPage() {
  const queryClient = useQueryClient()

  const approvalsQuery = useQuery({
    queryKey: ['lifeops', 'approvals'],
    queryFn: () => approvalsApi.listPending({ limit: 50 }),
    refetchInterval: 15_000,
  })

  const decide = useMutation({
    mutationFn: ({ id, approved }: { id: string; approved: boolean }) =>
      approvalsApi.decide(id, approved),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'approvals'] })
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'actions'] })
    },
  })

  if (approvalsQuery.isError) {
    return (
      <div className="p-8">
        <QueryError
          message={errorMessage(approvalsQuery.error)}
          onRetry={() => void approvalsQuery.refetch()}
        />
      </div>
    )
  }

  const approvals = approvalsQuery.data?.approvals ?? []

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-8">
      <header>
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <ShieldCheck className="h-5 w-5" />
          Approvals
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Every action with real consequence waits here for your decision before
          it happens.
        </p>
      </header>

      {approvalsQuery.isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading…
        </div>
      ) : approvals.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border/60 px-4 py-8 text-center text-sm text-muted-foreground">
          Nothing is waiting on your approval.
        </p>
      ) : (
        <div className="space-y-4">
          {approvals.map((approval) => (
            <ApprovalCard
              key={approval.id}
              approval={approval}
              onDecide={(approved) => decide.mutate({ id: approval.id, approved })}
              pendingDecision={decide.isPending && decide.variables?.id === approval.id}
            />
          ))}
        </div>
      )}
    </div>
  )
}
