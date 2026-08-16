/**
 * Waiting screen behaviour (BUILD_SPEC section 13).
 *
 * Phase 1 shows tasks in WAITING_EXTERNAL with what they are waiting on and
 * for how long. Full WaitingItems are Phase 4 — the screen must say so, not
 * fake them.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { WaitingPage } from '../WaitingPage'
import { tasksApi, type Task } from '@/services/lifeops'

vi.mock('@/services/lifeops', async () => {
  const actual = await vi.importActual<typeof import('@/services/lifeops')>(
    '@/services/lifeops',
  )
  return {
    ...actual,
    tasksApi: {
      list: vi.fn(),
      get: vi.fn(),
      create: vi.fn(),
      update: vi.fn(),
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

const mockedTasks = vi.mocked(tasksApi)

beforeEach(() => {
  mockedTasks.list.mockResolvedValue({
    tasks: [makeTask({ current_action: 'waiting for ABC Electric availability' })],
    total: 1,
    by_state: { WAITING_EXTERNAL: 1 },
  })
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('Waiting', () => {
  it('asks LifeOps for tasks in the waiting state', async () => {
    renderPage()
    expect(await screen.findByText('Book electrician')).toBeInTheDocument()
    expect(mockedTasks.list).toHaveBeenCalledWith({
      state: ['WAITING_EXTERNAL'],
      limit: 200,
    })
  })

  it('shows what each task is waiting on and for how long', async () => {
    renderPage()
    expect(
      await screen.findByText('Waiting: waiting for ABC Electric availability'),
    ).toBeInTheDocument()
    expect(screen.getByText(/^for /)).toBeInTheDocument()
  })

  it('falls back to a plain description when no action is recorded', async () => {
    mockedTasks.list.mockResolvedValue({
      tasks: [makeTask()],
      total: 1,
      by_state: { WAITING_EXTERNAL: 1 },
    })
    renderPage()
    expect(
      await screen.findByText('Waiting on an external response'),
    ).toBeInTheDocument()
  })

  it('links each waiting task to the Tasks screen', async () => {
    renderPage()
    const row = (await screen.findByText('Book electrician')).closest('a')
    expect(row).toHaveAttribute('href', '/tasks')
  })

  it('states that full waiting items arrive in Phase 4', async () => {
    renderPage()
    expect(await screen.findByText(/Phase 4/)).toBeInTheDocument()
  })

  it('has an honest empty state', async () => {
    mockedTasks.list.mockResolvedValue({ tasks: [], total: 0, by_state: {} })
    renderPage()
    expect(
      await screen.findByText('Nothing is waiting on the outside world.'),
    ).toBeInTheDocument()
  })

  it('explains an unreachable LifeOps Core rather than showing a bare error', async () => {
    mockedTasks.list.mockRejectedValue(new Error('Network Error'))
    renderPage()
    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument()
  })
})
