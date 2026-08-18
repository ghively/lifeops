/**
 * Calendar screen behaviour (BUILD_SPEC sections 10, 63, 96).
 *
 * Section 63's step order — read what's on the calendar, then the
 * Appointments LifeOps is driving, then a reversible hold — and the
 * "no calendar configured" graceful-degradation path for a fresh
 * deployment (section 88) are what's under test here.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { CalendarPage } from '../CalendarPage'
import {
  LifeOpsError,
  calendarApi,
  type Appointment,
  type CalendarEvent,
} from '@/services/lifeops'

vi.mock('@/services/lifeops', async () => {
  const actual = await vi.importActual<typeof import('@/services/lifeops')>(
    '@/services/lifeops',
  )
  return {
    ...actual,
    calendarApi: {
      listAppointments: vi.fn(),
      getAppointment: vi.fn(),
      readEvents: vi.fn(),
      hold: vi.fn(),
      book: vi.fn(),
      cancel: vi.fn(),
    },
  }
})

function makeAppointment(overrides: Partial<Appointment> = {}): Appointment {
  return {
    id: 'appt_01abc',
    subject: 'Electrician visit',
    status: 'HELD',
    provider_entity_id: 'provider_abc_electric',
    task_id: null,
    start_at: '2026-08-19T14:00:00Z',
    end_at: '2026-08-19T15:00:00Z',
    location: '',
    notes: '',
    calendar_provider_id: 'cal_provider_01',
    hold_reference: 'hold_ref_01',
    hold_expires_at: '2026-08-18T20:00:00Z',
    external_event_id: null,
    booking_action_id: null,
    created_at: '2026-08-18T10:00:00Z',
    ...overrides,
  }
}

function makeEvent(overrides: Partial<CalendarEvent> = {}): CalendarEvent {
  return {
    id: 'event_01abc',
    external_event_id: 'ext_01',
    calendar_provider_id: 'cal_provider_01',
    title: 'Team standup',
    start_at: '2026-08-19T09:00:00Z',
    end_at: '2026-08-19T09:30:00Z',
    location: '',
    ...overrides,
  }
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <CalendarPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const mockedCalendar = vi.mocked(calendarApi)

beforeEach(() => {
  mockedCalendar.listAppointments.mockResolvedValue({
    appointments: [makeAppointment()],
    total: 1,
  })
  mockedCalendar.readEvents.mockResolvedValue({ events: [makeEvent()], total: 1 })
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('Calendar', () => {
  it('shows appointments LifeOps is holding or has booked', async () => {
    renderPage()
    expect(await screen.findByText('Electrician visit')).toBeInTheDocument()
    expect(screen.getByText(/hold expires/)).toBeInTheDocument()
  })

  it('shows read-only events from the calendar', async () => {
    renderPage()
    expect(await screen.findByText('Team standup')).toBeInTheDocument()
  })

  it('requests a booking for a held appointment', async () => {
    mockedCalendar.book.mockResolvedValue({
      id: 'action_01',
      type: 'BOOK_APPOINTMENT',
      state: 'prepared',
    } as never)
    renderPage()
    await screen.findByText('Electrician visit')

    await userEvent.click(screen.getByRole('button', { name: /request booking/i }))

    await waitFor(() => expect(mockedCalendar.book).toHaveBeenCalledWith('appt_01abc'))
    await waitFor(() => expect(mockedCalendar.listAppointments).toHaveBeenCalledTimes(2))
  })

  it('cancels an appointment', async () => {
    mockedCalendar.cancel.mockResolvedValue({
      id: 'action_02',
      type: 'BOOK_APPOINTMENT',
      state: 'prepared',
    } as never)
    renderPage()
    await screen.findByText('Electrician visit')

    await userEvent.click(screen.getByRole('button', { name: /cancel/i }))

    await waitFor(() => expect(mockedCalendar.cancel).toHaveBeenCalledWith('appt_01abc'))
    await waitFor(() => expect(mockedCalendar.listAppointments).toHaveBeenCalledTimes(2))
  })

  it('surfaces a failed booking request instead of silently doing nothing', async () => {
    mockedCalendar.book.mockRejectedValue(
      new LifeOpsError('conflict', 'That hold has expired.', 409),
    )
    renderPage()
    await screen.findByText('Electrician visit')

    await userEvent.click(screen.getByRole('button', { name: /request booking/i }))

    expect(await screen.findByText('That hold has expired.')).toBeInTheDocument()
  })

  it('opens the hold form and submits a new hold', async () => {
    mockedCalendar.hold.mockResolvedValue(makeAppointment({ id: 'appt_02', subject: 'Plumber' }))
    renderPage()
    await screen.findByText('Electrician visit')

    await userEvent.click(screen.getByRole('button', { name: /hold a time/i }))
    await userEvent.type(screen.getByLabelText('Hold subject'), 'Plumber')
    await userEvent.type(screen.getByLabelText('Hold start'), '2026-08-20T10:00')
    await userEvent.type(screen.getByLabelText('Hold end'), '2026-08-20T11:00')

    await userEvent.click(screen.getByRole('button', { name: /^hold$/i }))

    await waitFor(() => expect(mockedCalendar.hold).toHaveBeenCalled())
    expect(mockedCalendar.hold).toHaveBeenCalledWith(
      expect.objectContaining({ subject: 'Plumber' }),
    )
  })

  it('treats no configured calendar provider as absent, not broken', async () => {
    mockedCalendar.listAppointments.mockRejectedValue(
      new LifeOpsError('configuration_error', 'Calendar is not configured.', 400),
    )
    mockedCalendar.readEvents.mockRejectedValue(
      new LifeOpsError('configuration_error', 'Calendar is not configured.', 400),
    )
    renderPage()

    expect(
      await screen.findByText(/no calendar provider is configured yet/i),
    ).toBeInTheDocument()
    expect(screen.queryByText('Electrician visit')).not.toBeInTheDocument()
  })

  it('has an honest empty state for appointments', async () => {
    mockedCalendar.listAppointments.mockResolvedValue({ appointments: [], total: 0 })
    renderPage()
    expect(await screen.findByText('No holds or bookings yet.')).toBeInTheDocument()
  })

  it('has an honest empty state for the read-only calendar window', async () => {
    mockedCalendar.readEvents.mockResolvedValue({ events: [], total: 0 })
    renderPage()
    expect(
      await screen.findByText(/nothing on the calendar in the next/i),
    ).toBeInTheDocument()
  })
})
