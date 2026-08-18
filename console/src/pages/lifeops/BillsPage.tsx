/**
 * Bills — what is owed, who is paid, and the approval boundary around moving
 * money (BUILD_SPEC sections 72, 99).
 *
 * Amounts are strings everywhere on this screen, never numbers. `89.10`
 * parsed through a JS number becomes `89.1`, and that value is hashed into an
 * approval a human agreed to (section 57). This file never parses an amount,
 * never calls `.toFixed`, and never does arithmetic on one — it only renders
 * the exact string LifeOps Core sent.
 *
 * A payee LifeOps returns from `POST /payees` is a proposal, not a usable
 * one (section 72: new payee always requires approval). This screen shows
 * every payee's approval state plainly and never lets a bill be recorded
 * without picking one, but a bill can still name an unapproved payee — it
 * simply cannot be paid until a human approves it, which the row makes clear.
 *
 * Preparing a payment always returns `needs_approval` (section 72, R4 is
 * never policy-relaxable). This screen never implies a payment happened; it
 * points at the Approvals screen where the decision actually gets made.
 *
 * LifeOps decides what is permitted — whether a bill is payable, whether a
 * payee is approved. This screen reads those flags off the server response;
 * it does not derive its own copy of that logic.
 */

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { CheckCircle2, Landmark, Loader2, Plus, Receipt, ShieldCheck } from 'lucide-react'

import { QueryError } from '@/components/QueryError'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import {
  BILL_STATUS_LABELS,
  LifeOpsError,
  billsApi,
  errorMessage,
  payeesApi,
  type Bill,
  type BillStatus,
  type Payee,
} from '@/services/lifeops'

const OPEN_STATUSES: BillStatus[] = ['due', 'scheduled', 'overdue', 'disputed']

const STATUS_TONE: Record<BillStatus, string> = {
  due: 'text-muted-foreground',
  scheduled: 'text-blue-500',
  paid: 'text-emerald-600',
  overdue: 'text-red-600',
  disputed: 'text-amber-600',
  cancelled: 'text-muted-foreground line-through',
}

function formatDate(iso: string | null): string {
  if (!iso) return 'no due date'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  // A due date is stored as midnight UTC; rendering that instant in a
  // negative-offset zone shows the previous day. Format it in UTC so a bill
  // entered as due Aug 18 never displays as Aug 17.
  return date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  })
}

// --- propose a payee ---------------------------------------------------------

function ProposePayeeDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [displayName, setDisplayName] = useState('')
  const [providerEntityId, setProviderEntityId] = useState('')
  const [error, setError] = useState<string | null>(null)

  const reset = () => {
    setDisplayName('')
    setProviderEntityId('')
    setError(null)
  }

  const propose = useMutation({
    mutationFn: () =>
      payeesApi.propose({
        display_name: displayName.trim(),
        provider_entity_id: providerEntityId.trim() || undefined,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'payees'] })
      reset()
      onClose()
    },
    onError: (err) => {
      setError(err instanceof LifeOpsError ? err.message : 'Could not propose the payee.')
    },
  })

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          reset()
          onClose()
        }
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Propose a payee</DialogTitle>
          <DialogDescription>
            Section 72: a new payee always requires approval. This records a
            proposal — it will not be usable for payment until you approve it.
          </DialogDescription>
        </DialogHeader>

        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            if (displayName.trim()) propose.mutate()
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="payee-name">Name</Label>
            <Input
              id="payee-name"
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              placeholder="City Water Utility"
              disabled={propose.isPending}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="payee-provider">Provider entity ID (optional)</Label>
            <Input
              id="payee-provider"
              value={providerEntityId}
              onChange={(event) => setProviderEntityId(event.target.value)}
              placeholder="provider_city_water"
              disabled={propose.isPending}
            />
          </div>

          {error && (
            <p className="rounded border border-red-300 bg-red-50 px-2 py-1 text-xs text-red-700">
              {error}
            </p>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={propose.isPending}>
              Cancel
            </Button>
            <Button type="submit" disabled={!displayName.trim() || propose.isPending}>
              {propose.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Propose'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

// --- record a bill ------------------------------------------------------------

function RecordBillDialog({
  open,
  onClose,
  payees,
}: {
  open: boolean
  onClose: () => void
  payees: Payee[]
}) {
  const queryClient = useQueryClient()
  const [payeeId, setPayeeId] = useState('')
  const [description, setDescription] = useState('')
  const [amount, setAmount] = useState('')
  const [currency, setCurrency] = useState('USD')
  const [dueAt, setDueAt] = useState('')
  const [error, setError] = useState<string | null>(null)

  const reset = () => {
    setPayeeId('')
    setDescription('')
    setAmount('')
    setCurrency('USD')
    setDueAt('')
    setError(null)
  }

  const record = useMutation({
    mutationFn: () =>
      billsApi.record({
        payee_id: payeeId,
        description: description.trim(),
        amount: amount.trim(),
        currency: currency.trim() || undefined,
        due_at: dueAt ? `${dueAt}T00:00:00Z` : undefined,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'bills'] })
      reset()
      onClose()
    },
    onError: (err) => {
      setError(err instanceof LifeOpsError ? err.message : 'Could not record the bill.')
    },
  })

  const valid = payeeId !== '' && description.trim() !== '' && amount.trim() !== ''

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          reset()
          onClose()
        }
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Record a bill</DialogTitle>
          <DialogDescription>
            This tracks something owed. It pays nothing — paying is a
            separate, always-approved step.
          </DialogDescription>
        </DialogHeader>

        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            if (valid) record.mutate()
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="bill-payee">Payee</Label>
            <select
              id="bill-payee"
              className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm"
              value={payeeId}
              onChange={(event) => setPayeeId(event.target.value)}
              disabled={record.isPending}
            >
              <option value="">Select a payee…</option>
              {payees.map((payee) => (
                <option key={payee.id} value={payee.id}>
                  {payee.display_name}
                  {!payee.is_approved ? ' (unapproved)' : ''}
                </option>
              ))}
            </select>
            {payees.length === 0 && (
              <p className="text-xs text-muted-foreground">
                No payees yet — propose one first.
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="bill-description">Description</Label>
            <Input
              id="bill-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Electricity — August"
              disabled={record.isPending}
            />
          </div>

          <div className="flex gap-3">
            <div className="flex-1 space-y-1.5">
              <Label htmlFor="bill-amount">Amount</Label>
              <Input
                id="bill-amount"
                value={amount}
                onChange={(event) => setAmount(event.target.value)}
                placeholder="89.10"
                inputMode="decimal"
                disabled={record.isPending}
              />
            </div>
            <div className="w-24 space-y-1.5">
              <Label htmlFor="bill-currency">Currency</Label>
              <Input
                id="bill-currency"
                value={currency}
                onChange={(event) => setCurrency(event.target.value.toUpperCase())}
                maxLength={3}
                disabled={record.isPending}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="bill-due">Due date (optional)</Label>
            <Input
              id="bill-due"
              type="date"
              value={dueAt}
              onChange={(event) => setDueAt(event.target.value)}
              disabled={record.isPending}
            />
          </div>

          {error && (
            <p className="rounded border border-red-300 bg-red-50 px-2 py-1 text-xs text-red-700">
              {error}
            </p>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={record.isPending}>
              Cancel
            </Button>
            <Button type="submit" disabled={!valid || record.isPending}>
              {record.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Record'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

// --- settle a bill --------------------------------------------------------------

function SettleBillDialog({
  bill,
  onClose,
}: {
  bill: Bill | null
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [reference, setReference] = useState('')
  const [error, setError] = useState<string | null>(null)

  const settle = useMutation({
    mutationFn: (billId: string) => billsApi.settle(billId, reference.trim()),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'bills'] })
      setReference('')
      setError(null)
      onClose()
    },
    onError: (err) => {
      setError(err instanceof LifeOpsError ? err.message : 'Could not settle the bill.')
    },
  })

  return (
    <Dialog
      open={bill !== null}
      onOpenChange={(next) => {
        if (!next) {
          setReference('')
          setError(null)
          onClose()
        }
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Settle {bill?.description}</DialogTitle>
          <DialogDescription>
            Section 72: a bill is settled only with the provider's own
            confirmation. This is required — LifeOps will not mark a bill paid
            on its own belief.
          </DialogDescription>
        </DialogHeader>

        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            if (bill && reference.trim()) settle.mutate(bill.id)
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="settle-reference">Confirmation reference</Label>
            <Input
              id="settle-reference"
              value={reference}
              onChange={(event) => setReference(event.target.value)}
              placeholder="Confirmation number from the payee"
              disabled={settle.isPending}
              autoFocus
            />
          </div>

          {error && (
            <p className="rounded border border-red-300 bg-red-50 px-2 py-1 text-xs text-red-700">
              {error}
            </p>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={settle.isPending}>
              Cancel
            </Button>
            <Button type="submit" disabled={!reference.trim() || settle.isPending}>
              {settle.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Settle'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

// --- rows -----------------------------------------------------------------------

function PayeeRow({
  payee,
  onApprove,
  approving,
}: {
  payee: Payee
  onApprove: () => void
  approving: boolean
}) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-lg border border-border/60 bg-card px-4 py-3">
      <div className="min-w-0">
        <p className="font-medium">{payee.display_name}</p>
        <p
          className={cn(
            'mt-0.5 flex items-center gap-1 text-xs',
            payee.is_approved ? 'text-emerald-600' : 'text-amber-600',
          )}
        >
          {payee.is_approved ? (
            <>
              <ShieldCheck className="h-3 w-3" />
              Approved — bills may be paid to this payee
            </>
          ) : (
            'Awaiting approval — cannot be paid yet'
          )}
        </p>
      </div>
      {!payee.is_approved && (
        <Button variant="outline" size="sm" onClick={onApprove} disabled={approving}>
          {approving && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
          Approve
        </Button>
      )}
    </div>
  )
}

function BillRow({
  bill,
  payee,
  onPreparePayment,
  onSettle,
  preparing,
  prepareError,
}: {
  bill: Bill
  payee: Payee | undefined
  onPreparePayment: () => void
  onSettle: () => void
  preparing: boolean
  prepareError: string | null
}) {
  return (
    <div className="rounded-lg border border-l-4 border-border/60 bg-card px-4 py-3 border-l-border">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-medium">{bill.description}</p>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span className="font-mono text-sm text-foreground">
              {bill.amount} {bill.currency}
            </span>
            <span className={cn('font-medium', STATUS_TONE[bill.status])}>
              {BILL_STATUS_LABELS[bill.status]}
            </span>
            <span>{formatDate(bill.due_at)}</span>
            <span>to {payee?.display_name ?? bill.payee_id}</span>
            {payee && !payee.is_approved && (
              <span className="text-amber-600">payee not yet approved</span>
            )}
            {bill.external_reference && <span>ref {bill.external_reference}</span>}
          </div>
        </div>

        {bill.is_payable && (
          <div className="flex shrink-0 gap-1.5">
            <Button variant="outline" size="sm" disabled={preparing} onClick={onPreparePayment}>
              {preparing && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
              Prepare payment
            </Button>
            <Button variant="ghost" size="sm" onClick={onSettle}>
              <CheckCircle2 className="mr-1 h-3.5 w-3.5" />
              Settle
            </Button>
          </div>
        )}
      </div>

      {prepareError && (
        <p className="mt-2 rounded border border-red-300 bg-red-50 px-2 py-1 text-xs text-red-700">
          {prepareError}
        </p>
      )}
    </div>
  )
}

// --- page -----------------------------------------------------------------------

export function BillsPage() {
  const queryClient = useQueryClient()
  const [payeeDialogOpen, setPayeeDialogOpen] = useState(false)
  const [billDialogOpen, setBillDialogOpen] = useState(false)
  const [settleTarget, setSettleTarget] = useState<Bill | null>(null)
  const [preparedNotice, setPreparedNotice] = useState<string | null>(null)
  const [prepareErrors, setPrepareErrors] = useState<Record<string, string>>({})

  const payeesQuery = useQuery({
    queryKey: ['lifeops', 'payees'],
    queryFn: () => payeesApi.list(),
  })

  const billsQuery = useQuery({
    queryKey: ['lifeops', 'bills'],
    queryFn: () => billsApi.list({ limit: 200 }),
  })

  const approvePayee = useMutation({
    mutationFn: (id: string) => payeesApi.approve(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'payees'] })
    },
  })

  const preparePayment = useMutation({
    mutationFn: (billId: string) => billsApi.preparePayment(billId),
    onSuccess: (_data, billId) => {
      setPrepareErrors((prev) => {
        const next = { ...prev }
        delete next[billId]
        return next
      })
      setPreparedNotice('Payment prepared — it needs your approval before anything is sent.')
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'bills'] })
    },
    onError: (err, billId) => {
      const message =
        err instanceof LifeOpsError ? err.message : 'Could not prepare the payment.'
      setPrepareErrors((prev) => ({ ...prev, [billId]: message }))
    },
  })

  if (payeesQuery.isError || billsQuery.isError) {
    return (
      <div className="p-8">
        <QueryError
          message={errorMessage(payeesQuery.error ?? billsQuery.error)}
          onRetry={() => {
            void payeesQuery.refetch()
            void billsQuery.refetch()
          }}
        />
      </div>
    )
  }

  const payees = payeesQuery.data?.payees ?? []
  const bills = billsQuery.data?.bills ?? []
  const payeeById = new Map(payees.map((p) => [p.id, p]))
  const openBills = bills.filter((b) => OPEN_STATUSES.includes(b.status))
  const closedBills = bills.filter((b) => !OPEN_STATUSES.includes(b.status))

  return (
    <div className="mx-auto max-w-3xl space-y-8 p-8">
      <header>
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <Receipt className="h-5 w-5" />
          Bills
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          What is owed, to whom, and what has been paid. Paying money is
          always a human decision — this screen prepares, it never sends.
        </p>
      </header>

      {preparedNotice && (
        <div className="flex items-center justify-between gap-4 rounded-lg border border-blue-300 bg-blue-50 px-4 py-3 text-sm text-blue-800 dark:border-blue-900 dark:bg-blue-950/30 dark:text-blue-300">
          <span>{preparedNotice}</span>
          <Button variant="outline" size="sm" asChild>
            <Link to="/approvals">
              <ShieldCheck className="mr-1.5 h-3.5 w-3.5" />
              Go to Approvals
            </Link>
          </Button>
        </div>
      )}

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
            <Landmark className="h-4 w-4" />
            Payees
          </h2>
          <Button variant="outline" size="sm" onClick={() => setPayeeDialogOpen(true)}>
            <Plus className="mr-1 h-3.5 w-3.5" />
            Propose payee
          </Button>
        </div>

        {payeesQuery.isLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading…
          </div>
        ) : payees.length === 0 ? (
          <p className="rounded-lg border border-dashed border-border/60 px-4 py-6 text-center text-sm text-muted-foreground">
            No payees yet.
          </p>
        ) : (
          <div className="space-y-2">
            {payees.map((payee) => (
              <PayeeRow
                key={payee.id}
                payee={payee}
                onApprove={() => approvePayee.mutate(payee.id)}
                approving={approvePayee.isPending && approvePayee.variables === payee.id}
              />
            ))}
          </div>
        )}
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground">
            Bills
          </h2>
          <Button variant="outline" size="sm" onClick={() => setBillDialogOpen(true)}>
            <Plus className="mr-1 h-3.5 w-3.5" />
            Record a bill
          </Button>
        </div>

        {billsQuery.isLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading…
          </div>
        ) : bills.length === 0 ? (
          <p className="rounded-lg border border-dashed border-border/60 px-4 py-8 text-center text-sm text-muted-foreground">
            Nothing recorded yet.
          </p>
        ) : (
          <div className="space-y-2">
            {[...openBills, ...closedBills].map((bill) => (
              <BillRow
                key={bill.id}
                bill={bill}
                payee={payeeById.get(bill.payee_id)}
                onPreparePayment={() => preparePayment.mutate(bill.id)}
                onSettle={() => setSettleTarget(bill)}
                preparing={preparePayment.isPending && preparePayment.variables === bill.id}
                prepareError={prepareErrors[bill.id] ?? null}
              />
            ))}
          </div>
        )}
      </section>

      <ProposePayeeDialog open={payeeDialogOpen} onClose={() => setPayeeDialogOpen(false)} />
      <RecordBillDialog
        open={billDialogOpen}
        onClose={() => setBillDialogOpen(false)}
        payees={payees}
      />
      <SettleBillDialog bill={settleTarget} onClose={() => setSettleTarget(null)} />
    </div>
  )
}
