/**
 * Today screen behaviour (BUILD_SPEC section 11).
 *
 * The audit found this screen showed tasks only, despite the spec asking
 * for approvals, waiting items, and calendar events too. What's under test:
 * pending approvals render with a Review link, active waiting items render,
 * today's appointments render (and non-today ones don't), and a
 * not-configured calendar degrades quietly rather than throwing.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { TodayPage } from '../TodayPage'
import {
  LifeOpsError,
  approvalsApi,
  calendarApi,
  peopleApi,
  tasksApi,
  waitingApi,
  type Approval,
  type Appointment,
  type Task,
  type WaitingItem,
} from '@/services/lifeops'

vi.mock('@/services/lifeops', async () => {
  const actual = await vi.importActual<typeof import('@/services/lifeops')>(
    '@/services/lifeops',
  )
  return {
    ...actual,
    tasksApi: { list: vi.fn() },
    peopleApi: { me: vi.fn() },
    approvalsApi: { listPending: vi.fn() },
    waitingApi: { list: vi.fn() },
    calendarApi: { listAppointments: vi.fn() },
  }
})

function makeApproval(overrides: Partial<Approval> = {}): Approval {
  return {
    id: 'approval_01',
    action_id: 'action_01',
    payload_hash: 'hash',
    requested_by: 'hermes-personal',
    approved_by: null,
    approved_at: null,
    expires_at: '2026-08-17T10:00:00Z',
    consumed_at: null,
    status: 'pending',
    action_type: 'book_appointment',
    authorises_action: 'booking the electrician',
    does_not_authorise: [],
    target_entity_id: null,
    amount: '89.00',
    created_at: '2026-08-16T10:00:00Z',
    action_payload: {},
    action_status: 'needs_approval',
    ...overrides,
  }
}

function makeWaitingItem(overrides: Partial<WaitingItem> = {}): WaitingItem {
  return {
    id: 'waiting_01',
    task_id: 'task_01',
    subject: 'Dentist office response',
    waiting_on_entity_id: null,
    waiting_since: '2026-08-16T08:00:00Z',
    expected_by: null,
    next_action_at: null,
    last_contact_at: null,
    followup_count: 0,
    max_followups: 3,
    status: 'waiting',
    attempt_count: 0,
    lease_owner: null,
    lease_until: null,
    created_by_client: 'hermes-personal',
    ...overrides,
  }
}

function makeAppointment(overrides: Partial<Appointment> = {}): Appointment {
  return {
    id: 'appointment_01',
    subject: 'Dentist',
    status: 'HELD',
    provider_entity_id: null,
    task_id: null,
    start_at: new Date().toISOString(),
    end_at: new Date().toISOString(),
    location: '',
    notes: '',
    calendar_provider_id: 'calendar',
    hold_reference: null,
    hold_expires_at: null,
    external_event_id: null,
    booking_action_id: null,
    created_at: '2026-08-16T08:00:00Z',
    ...overrides,
  }
}

function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task_01',
    title: 'Repair living room outlet',
    description: null,
    state: 'CAPTURED',
    priority: 'medium',
    created_at: '2026-08-16T10:00:00Z',
    updated_at: '2026-08-16T10:00:00Z',
    due_at: null,
    owner_entity_id: 'person_gene',
    assigned_client: null,
    current_action: null,
    waiting_item_id: null,
    verification_required: false,
    verification_state: 'not_required',
    verification_evidence: null,
    related_entity_ids: [],
    source: null,
    created_by_client: 'hermes-personal',
    needs_attention: false,
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
        <TodayPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const mockedTasks = vi.mocked(tasksApi)
const mockedPeople = vi.mocked(peopleApi)
const mockedApprovals = vi.mocked(approvalsApi)
const mockedWaiting = vi.mocked(waitingApi)
const mockedCalendar = vi.mocked(calendarApi)

beforeEach(() => {
  mockedTasks.list.mockResolvedValue({ tasks: [], total: 0, by_state: {} })
  mockedPeople.me.mockResolvedValue({
    id: 'person_gene',
    display_name: 'Gene',
    is_primary: true,
    aliases: [],
    timezone: 'America/Chicago',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  })
  mockedApprovals.listPending.mockResolvedValue({ approvals: [], total: 0 })
  mockedWaiting.list.mockResolvedValue({ items: [], total: 0 })
  mockedCalendar.listAppointments.mockResolvedValue({ appointments: [], total: 0 })
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('Today', () => {
  it('renders pending approvals with a Review affordance', async () => {
    mockedApprovals.listPending.mockResolvedValue({
      approvals: [makeApproval()],
      total: 1,
    })
    renderPage()

    expect(
      await screen.findByRole('heading', { name: 'Needs your approval' }),
    ).toBeInTheDocument()
    expect(screen.getByText('book_appointment')).toBeInTheDocument()
    expect(screen.getByText('Review')).toBeInTheDocument()
    expect(screen.getByText('Review').closest('a')).toHaveAttribute(
      'href',
      '/approvals',
    )
  })

  it('renders active waiting items', async () => {
    mockedWaiting.list.mockResolvedValue({
      items: [makeWaitingItem()],
      total: 1,
    })
    renderPage()

    expect(
      await screen.findByRole('heading', { name: 'Waiting on others' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Dentist office response')).toBeInTheDocument()
    await waitFor(() =>
      expect(mockedWaiting.list).toHaveBeenCalledWith({
        status: ['waiting', 'escalated'],
      }),
    )
  })

  it("shows today's appointments and excludes ones on other days", async () => {
    const today = new Date()
    const yesterday = new Date(today.getTime() - 86_400_000)
    mockedCalendar.listAppointments.mockResolvedValue({
      appointments: [
        makeAppointment({ id: 'appt_today', subject: 'Dentist', start_at: today.toISOString() }),
        makeAppointment({
          id: 'appt_yesterday',
          subject: 'Old checkup',
          start_at: yesterday.toISOString(),
        }),
      ],
      total: 2,
    })
    renderPage()

    expect(
      await screen.findByRole('heading', { name: "Today's calendar" }),
    ).toBeInTheDocument()
    expect(screen.getByText('Dentist')).toBeInTheDocument()
    expect(screen.queryByText('Old checkup')).not.toBeInTheDocument()
  })

  it('degrades quietly when no calendar provider is configured', async () => {
    mockedCalendar.listAppointments.mockRejectedValue(
      new LifeOpsError('configuration_error', 'no calendar provider is configured', 400),
    )
    renderPage()

    // The task-derived sections still render; no error banner appears for
    // the calendar section specifically.
    expect(await screen.findByRole('heading', { name: 'Needs you' })).toBeInTheDocument()
    expect(
      screen.queryByRole('heading', { name: "Today's calendar" }),
    ).not.toBeInTheDocument()
    expect(screen.queryByText(/something went wrong/i)).not.toBeInTheDocument()
  })

  it('still shows the task-derived sections', async () => {
    mockedTasks.list.mockResolvedValue({
      tasks: [makeTask({ state: 'COMPLETED' })],
      total: 1,
      by_state: {},
    })
    renderPage()

    expect(
      await screen.findByRole('heading', { name: 'Recently completed' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Repair living room outlet')).toBeInTheDocument()
  })
})
