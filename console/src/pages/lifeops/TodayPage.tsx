/**
 * Today — the default LifeOps Console screen (BUILD_SPEC section 11).
 *
 * Shows what needs attention, what is in progress, and what recently
 * completed, plus the three groups the audit found missing: pending
 * approvals, waiting items, and today's calendar. Calendar is treated as
 * absent rather than broken when no provider is configured — a
 * `configuration_error` there is the expected shape of "nothing set up
 * yet," not a failure.
 */

import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  AlertCircle,
  CalendarClock,
  CheckCircle2,
  Clock,
  Loader2,
  ShieldQuestion,
} from 'lucide-react'

import { QueryError } from '@/components/QueryError'
import {
  TASK_STATE_LABELS,
  approvalsApi,
  calendarApi,
  errorMessage,
  peopleApi,
  tasksApi,
  waitingApi,
  type Approval,
  type Appointment,
  type Task,
  type WaitingItem,
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

function ApprovalRow({ approval }: { approval: Approval }) {
  return (
    <Link
      to="/approvals"
      className="flex items-start justify-between gap-4 rounded-lg border border-border/60 px-4 py-3 transition-colors hover:bg-muted/50"
    >
      <div className="min-w-0">
        <p className="truncate font-medium">{approval.action_type}</p>
        <p className="mt-0.5 text-sm text-muted-foreground">
          {approval.amount ? `${approval.amount} · ` : ''}Approval required
        </p>
      </div>
      <span className="shrink-0 rounded-md border border-border/60 px-2 py-1 text-xs font-medium">
        Review
      </span>
    </Link>
  )
}

function WaitingRow({ item }: { item: WaitingItem }) {
  return (
    <Link
      to="/waiting"
      className="flex items-start justify-between gap-4 rounded-lg border border-border/60 px-4 py-3 transition-colors hover:bg-muted/50"
    >
      <div className="min-w-0">
        <p className="truncate font-medium">{item.subject}</p>
        <p className="mt-0.5 text-sm text-muted-foreground">
          Waiting since {new Date(item.waiting_since).toLocaleDateString()}
          {item.status === 'escalated' ? ' · escalated' : ''}
        </p>
      </div>
    </Link>
  )
}

function AppointmentRow({ appointment }: { appointment: Appointment }) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-lg border border-border/60 px-4 py-3">
      <div className="min-w-0">
        <p className="truncate font-medium">{appointment.subject}</p>
        {appointment.location && (
          <p className="mt-0.5 text-sm text-muted-foreground">{appointment.location}</p>
        )}
      </div>
      <span className="shrink-0 text-xs uppercase tracking-wide text-muted-foreground">
        {new Date(appointment.start_at).toLocaleTimeString(undefined, {
          hour: 'numeric',
          minute: '2-digit',
        })}
      </span>
    </div>
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
  const approvalsQuery = useQuery({
    queryKey: ['lifeops', 'approvals', 'pending'],
    queryFn: () => approvalsApi.listPending(),
    refetchInterval: 30_000,
    // A client without APPROVE_ACTION (everyone but the Console) still
    // reads this fine — capability denial there would be a real error, not
    // an absent-provider one, so this stays a normal retry-and-surface.
  })
  const waitingQuery = useQuery({
    queryKey: ['lifeops', 'waiting', 'active'],
    queryFn: () => waitingApi.list({ status: ['waiting', 'escalated'] }),
    refetchInterval: 30_000,
  })
  const calendarQuery = useQuery({
    queryKey: ['lifeops', 'appointments'],
    queryFn: () => calendarApi.listAppointments(),
    retry: false,
    // No calendar provider configured is the expected shape of a fresh
    // deployment (BUILD_SPEC section 88): rather than branch on isError,
    // this section is simply read from `.data`, which stays undefined on
    // any failure — "no calendar" reads the same as "not configured yet"
    // instead of surfacing a 400 as if something broke.
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

  const pendingApprovals = approvalsQuery.data?.approvals ?? []
  const activeWaiting = waitingQuery.data?.items ?? []
  const todayStr = new Date().toDateString()
  const todaysAppointments = (calendarQuery.data?.appointments ?? [])
    .filter((a) => new Date(a.start_at).toDateString() === todayStr)
    .sort((a, b) => a.start_at.localeCompare(b.start_at))

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
          {pendingApprovals.length > 0 && (
            <section className="space-y-3">
              <h2 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                <ShieldQuestion className="h-3.5 w-3.5" />
                Needs your approval
              </h2>
              <div className="space-y-2">
                {pendingApprovals.map((approval) => (
                  <ApprovalRow key={approval.id} approval={approval} />
                ))}
              </div>
            </section>
          )}

          <Section
            title="Needs you"
            icon={AlertCircle}
            tasks={needsAttention}
            empty="Nothing is waiting on you."
          />

          {activeWaiting.length > 0 && (
            <section className="space-y-3">
              <h2 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                <Clock className="h-3.5 w-3.5" />
                Waiting on others
              </h2>
              <div className="space-y-2">
                {activeWaiting.map((item) => (
                  <WaitingRow key={item.id} item={item} />
                ))}
              </div>
            </section>
          )}

          <Section
            title="In progress"
            icon={Loader2}
            tasks={inProgress}
            empty="Nothing is in flight."
          />

          {todaysAppointments.length > 0 && (
            <section className="space-y-3">
              <h2 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                <CalendarClock className="h-3.5 w-3.5" />
                Today's calendar
              </h2>
              <div className="space-y-2">
                {todaysAppointments.map((appointment) => (
                  <AppointmentRow key={appointment.id} appointment={appointment} />
                ))}
              </div>
            </section>
          )}

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
        <p>
          This is a visual surface for LifeOps state — not a replacement for
          talking to Hermes.
        </p>
      </footer>
    </div>
  )
}
