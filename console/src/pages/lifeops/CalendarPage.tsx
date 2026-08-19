/**
 * Calendar — availability, holds, and bookings (BUILD_SPEC sections 10, 63,
 * 96). Section 10 lists Calendar as a top-level nav entry; no section gives
 * it its own screen spec the way Today or Waiting get one, so this follows
 * section 63's own step order: read what's on the calendar, then the
 * Appointments LifeOps is actively driving (holds and bookings), then a
 * reversible hold as the one write this screen offers directly.
 *
 * Booking and cancelling only *record intent* through the action outbox —
 * approving and executing happen on the Approvals/Actions screens, the same
 * boundary every other external action in LifeOps draws (section 57).
 *
 * No calendar provider configured (the default on a fresh deployment, per
 * section 88) is treated as an absent calendar, not a broken screen: the
 * queries are read from `.data`, which stays undefined on that expected
 * failure, rather than branching on isError.
 */

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarDays, Loader2, Plus } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import {
  LifeOpsError,
  calendarApi,
  errorMessage,
  type Appointment,
  type CalendarEvent,
} from '@/services/lifeops'

const READ_WINDOW_DAYS = 14

function formatDateTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

const STATUS_LABEL: Record<string, string> = {
  HELD: 'Held',
  BOOKED: 'Booked',
  CANCELLED: 'Cancelled',
}

function AppointmentRow({
  appointment,
  onBook,
  onCancel,
  bookPending,
  cancelPending,
}: {
  appointment: Appointment
  onBook: () => void
  onCancel: () => void
  bookPending: boolean
  cancelPending: boolean
}) {
  const canBook = appointment.status === 'HELD'
  const canCancel = appointment.status === 'HELD' || appointment.status === 'BOOKED'
  return (
    <div className="rounded-lg border border-border/60 bg-card px-4 py-3">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <p className="font-medium">{appointment.subject}</p>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {formatDateTime(appointment.start_at)} – {formatDateTime(appointment.end_at)}
          </p>
          {appointment.location && (
            <p className="mt-0.5 text-sm text-muted-foreground">{appointment.location}</p>
          )}
          <p
            className={cn(
              'mt-1.5 text-xs font-medium',
              appointment.status === 'BOOKED'
                ? 'text-emerald-600'
                : appointment.status === 'CANCELLED'
                  ? 'text-muted-foreground'
                  : 'text-amber-600',
            )}
          >
            {STATUS_LABEL[appointment.status] ?? appointment.status}
            {appointment.hold_expires_at && appointment.status === 'HELD'
              ? ` · hold expires ${formatDateTime(appointment.hold_expires_at)}`
              : ''}
          </p>
        </div>
        {(canBook || canCancel) && (
          <div className="flex shrink-0 flex-col gap-1.5">
            {canBook && (
              <Button variant="outline" size="sm" disabled={bookPending} onClick={onBook}>
                {bookPending && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
                Request booking
              </Button>
            )}
            {canCancel && (
              <Button variant="ghost" size="sm" disabled={cancelPending} onClick={onCancel}>
                Cancel
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function EventRow({ event }: { event: CalendarEvent }) {
  return (
    <div className="rounded-lg border border-border/60 px-4 py-2.5 text-sm">
      <p className="font-medium">{event.title}</p>
      <p className="mt-0.5 text-xs text-muted-foreground">
        {formatDateTime(event.start_at)} – {formatDateTime(event.end_at)}
        {event.location ? ` · ${event.location}` : ''}
      </p>
    </div>
  )
}

export function CalendarPage() {
  const queryClient = useQueryClient()
  const [holdOpen, setHoldOpen] = useState(false)
  const [subject, setSubject] = useState('')
  const [startAt, setStartAt] = useState('')
  const [endAt, setEndAt] = useState('')
  const [holdError, setHoldError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const now = new Date()
  const windowEnd = new Date(now.getTime() + READ_WINDOW_DAYS * 86_400_000)

  const eventsQuery = useQuery({
    queryKey: ['lifeops', 'calendar', 'events'],
    queryFn: () =>
      calendarApi.readEvents({ start_at: now.toISOString(), end_at: windowEnd.toISOString() }),
    retry: false,
  })

  const appointmentsQuery = useQuery({
    queryKey: ['lifeops', 'appointments'],
    queryFn: () => calendarApi.listAppointments(),
    retry: false,
    refetchInterval: 30_000,
  })

  const invalidateAppointments = () =>
    queryClient.invalidateQueries({ queryKey: ['lifeops', 'appointments'] })

  const hold = useMutation({
    mutationFn: () =>
      calendarApi.hold({
        subject,
        start_at: new Date(startAt).toISOString(),
        end_at: new Date(endAt).toISOString(),
      }),
    onSuccess: () => {
      setHoldOpen(false)
      setSubject('')
      setStartAt('')
      setEndAt('')
      setHoldError(null)
      invalidateAppointments()
    },
    onError: (error) => {
      setHoldError(
        error instanceof LifeOpsError ? error.message : 'Could not hold that time.',
      )
    },
  })

  const book = useMutation({
    mutationFn: (id: string) => calendarApi.book(id),
    onSuccess: () => {
      setActionError(null)
      invalidateAppointments()
    },
    onError: (error) => {
      setActionError(
        error instanceof LifeOpsError ? error.message : 'Could not request the booking.',
      )
    },
  })

  const cancel = useMutation({
    mutationFn: (id: string) => calendarApi.cancel(id),
    onSuccess: () => {
      setActionError(null)
      invalidateAppointments()
    },
    onError: (error) => {
      setActionError(
        error instanceof LifeOpsError ? error.message : 'Could not cancel the appointment.',
      )
    },
  })

  const events = eventsQuery.data?.events ?? []
  const appointments = appointmentsQuery.data?.appointments ?? []
  const noCalendarConfigured =
    !eventsQuery.isLoading &&
    !appointmentsQuery.isLoading &&
    eventsQuery.isError &&
    appointmentsQuery.isError

  return (
    <div className="mx-auto max-w-3xl space-y-8 p-8">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <CalendarDays className="h-5 w-5" />
            Calendar
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            What's on the calendar, and the appointments LifeOps is holding or
            has booked.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => setHoldOpen((current) => !current)}>
          <Plus className="mr-1 h-4 w-4" />
          Hold a time
        </Button>
      </header>

      {noCalendarConfigured ? (
        <p className="rounded-lg border border-dashed border-border/60 px-4 py-8 text-center text-sm text-muted-foreground">
          No calendar provider is configured yet. Set one up in Configuration
          to see events and appointments here.
        </p>
      ) : (
        <>
          {holdOpen && (
            <form
              className="space-y-2 rounded-lg border border-border/60 bg-card px-4 py-4"
              onSubmit={(event) => {
                event.preventDefault()
                if (subject.trim() && startAt && endAt) hold.mutate()
              }}
            >
              <Input
                value={subject}
                onChange={(event) => setSubject(event.target.value)}
                placeholder="Subject, e.g. 'Electrician visit'"
                aria-label="Hold subject"
                disabled={hold.isPending}
              />
              <div className="flex gap-2">
                {/* State stays in the input's own YYYY-MM-DDTHH:mm form and
                    converts to ISO only at submit. Feeding an ISO string back
                    as the controlled value blanked the field (invalid for
                    datetime-local), and converting inside onChange threw on a
                    cleared/partial value — leaving stale hidden state that
                    submitted the previous time (2026-08-18 audit). */}
                <Input
                  type="datetime-local"
                  value={startAt}
                  onChange={(event) => setStartAt(event.target.value)}
                  aria-label="Hold start"
                  disabled={hold.isPending}
                />
                <Input
                  type="datetime-local"
                  value={endAt}
                  onChange={(event) => setEndAt(event.target.value)}
                  aria-label="Hold end"
                  disabled={hold.isPending}
                />
              </div>
              <p className="text-xs text-muted-foreground">
                A reversible write, not a booking (section 63) — requesting a
                booking afterward is a separate, approval-gated step.
              </p>
              <div className="flex gap-2">
                <Button
                  type="submit"
                  size="sm"
                  disabled={!subject.trim() || !startAt || !endAt || hold.isPending}
                >
                  {hold.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Hold'}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setHoldOpen(false)}
                  disabled={hold.isPending}
                >
                  Cancel
                </Button>
              </div>
              {holdError && (
                <p className="rounded border border-red-300 bg-red-50 px-2 py-1 text-xs text-red-700">
                  {holdError}
                </p>
              )}
            </form>
          )}

          {actionError && (
            <p
              role="alert"
              className="rounded-lg border border-red-300/60 bg-red-50 px-4 py-2 text-sm text-red-700 dark:border-red-800/60 dark:bg-red-950/40 dark:text-red-300"
            >
              {actionError}
            </p>
          )}

          <section className="space-y-3">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
              Appointments
            </h2>
            {appointmentsQuery.isLoading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading…
              </div>
            ) : appointments.length === 0 ? (
              <p className="rounded-lg border border-dashed border-border/60 px-4 py-6 text-center text-sm text-muted-foreground">
                No holds or bookings yet.
              </p>
            ) : (
              <div className="space-y-2">
                {appointments.map((appointment) => (
                  <AppointmentRow
                    key={appointment.id}
                    appointment={appointment}
                    onBook={() => book.mutate(appointment.id)}
                    onCancel={() => cancel.mutate(appointment.id)}
                    bookPending={book.isPending && book.variables === appointment.id}
                    cancelPending={cancel.isPending && cancel.variables === appointment.id}
                  />
                ))}
              </div>
            )}
          </section>

          <section className="space-y-3">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
              On the calendar
            </h2>
            <p className="text-xs text-muted-foreground">
              Read-only, the next {READ_WINDOW_DAYS} days — everything on the
              calendar, not only what LifeOps booked.
            </p>
            {eventsQuery.isLoading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading…
              </div>
            ) : eventsQuery.isError ? (
              <p className="rounded-lg border border-dashed border-border/60 px-4 py-6 text-center text-sm text-muted-foreground">
                {errorMessage(eventsQuery.error)}
              </p>
            ) : events.length === 0 ? (
              <p className="rounded-lg border border-dashed border-border/60 px-4 py-6 text-center text-sm text-muted-foreground">
                Nothing on the calendar in the next {READ_WINDOW_DAYS} days.
              </p>
            ) : (
              <div className="space-y-2">
                {events.map((event) => (
                  <EventRow key={event.id} event={event} />
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  )
}
