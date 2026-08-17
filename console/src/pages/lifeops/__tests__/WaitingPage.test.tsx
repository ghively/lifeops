/**
 * Waiting screen behaviour (BUILD_SPEC section 13).
 *
 * Phase 4: the screen renders real WaitingItems — subject, task, waiting on,
 * waiting since, expected response, next follow-up, follow-up count, and
 * escalation state — and submits follow-up/resolve decisions to LifeOps
 * Core rather than computing anything itself.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { WaitingPage } from '../WaitingPage'
import { tasksApi, waitingApi, type Task, type WaitingItem } from '@/services/lifeops'

vi.mock('@/services/lifeops', async () => {
  const actual = await vi.importActual<typeof import('@/services/lifeops')>(
    '@/services/lifeops',
  )
  return {
    ...actual,
    tasksApi: {
      ...actual.tasksApi,
      get: vi.fn(),
    },
    waitingApi: {
      list: vi.fn(),
      get: vi.fn(),
      create: vi.fn(),
      followUp: vi.fn(),
      resolve: vi.fn(),
    },
  }
})

function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task_01abc',
    title: 'Book electrician',
    description: null,
    state: 'WAITING_EXTERNAL',
    priority: 'medium',
    created_at: '2026-08-16T08:00:00Z',
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

function makeWaitingItem(overrides: Partial<WaitingItem> = {}): WaitingItem {
  return {
    id: 'waiting_01abc',
    task_id: 'task_01abc',
    subject: 'ABC Electric',
    waiting_on_entity_id: 'provider_abc_electric',
    waiting_since: '2026-08-16T08:00:00Z',
    expected_by: '2026-08-20T00:00:00Z',
    next_action_at: '2026-08-18T08:00:00Z',
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

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <WaitingPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const mockedWaiting = vi.mocked(waitingApi)
const mockedTasks = vi.mocked(tasksApi)

beforeEach(() => {
  mockedWaiting.list.mockResolvedValue({ items: [makeWaitingItem()], total: 1 })
  mockedTasks.get.mockResolvedValue(makeTask())
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('Waiting', () => {
  it('asks LifeOps for the active waiting items', async () => {
    renderPage()
    expect(await screen.findByText('ABC Electric')).toBeInTheDocument()
    expect(mockedWaiting.list).toHaveBeenCalledWith({
      status: ['waiting', 'escalated'],
      limit: 200,
    })
  })

  it('shows subject, task, waiting on, and follow-up count', async () => {
    renderPage()
    expect(await screen.findByText('ABC Electric')).toBeInTheDocument()
    expect(await screen.findByText('Book electrician')).toBeInTheDocument()
    expect(screen.getByText('provider_abc_electric')).toBeInTheDocument()
    expect(screen.getByText('0 of 3 follow-ups')).toBeInTheDocument()
  })

  it('shows escalation state', async () => {
    mockedWaiting.list.mockResolvedValue({
      items: [makeWaitingItem({ status: 'escalated', next_action_at: null })],
      total: 1,
    })
    renderPage()
    expect(await screen.findByText('Escalated — needs you')).toBeInTheDocument()
  })

  it('logs a follow-up and refetches', async () => {
    mockedWaiting.followUp.mockResolvedValue(
      makeWaitingItem({ followup_count: 1 }),
    )
    renderPage()
    await screen.findByText('ABC Electric')

    await userEvent.click(screen.getByRole('button', { name: /log follow-up/i }))

    await waitFor(() => expect(mockedWaiting.followUp).toHaveBeenCalledWith('waiting_01abc'))
    await waitFor(() => expect(mockedWaiting.list).toHaveBeenCalledTimes(2))
  })

  it('marks an item resolved and refetches', async () => {
    mockedWaiting.resolve.mockResolvedValue(makeWaitingItem({ status: 'resolved' }))
    renderPage()
    await screen.findByText('ABC Electric')

    await userEvent.click(screen.getByRole('button', { name: /mark resolved/i }))

    await waitFor(() => expect(mockedWaiting.resolve).toHaveBeenCalledWith('waiting_01abc'))
    await waitFor(() => expect(mockedWaiting.list).toHaveBeenCalledTimes(2))
  })

  it('has an honest empty state', async () => {
    mockedWaiting.list.mockResolvedValue({ items: [], total: 0 })
    renderPage()
    expect(
      await screen.findByText('Nothing is waiting on the outside world.'),
    ).toBeInTheDocument()
  })

  it('explains an unreachable LifeOps Core rather than showing a bare error', async () => {
    mockedWaiting.list.mockRejectedValue(new Error('Network Error'))
    renderPage()
    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument()
  })
})
