/**
 * Tasks screen behaviour.
 *
 * The important property is that the Console offers only transitions the
 * LifeOps state machine permits, and that when the server refuses one anyway
 * the UI shows the server's reason instead of the state it hoped for.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { LifeOpsTasksPage } from '../TasksPage'
import { LifeOpsError, tasksApi, type Task } from '@/services/lifeops'

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
    title: 'Call dentist',
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
        <LifeOpsTasksPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const mockedTasks = vi.mocked(tasksApi)

beforeEach(() => {
  mockedTasks.list.mockResolvedValue({
    tasks: [makeTask()],
    total: 1,
    by_state: { CAPTURED: 1 },
  })
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('LifeOps Tasks', () => {
  it('renders tasks from LifeOps Core', async () => {
    renderPage()
    expect(await screen.findByText('Call dentist')).toBeInTheDocument()
    expect(screen.getByText('Captured')).toBeInTheDocument()
  })

  it('shows which client created the task', async () => {
    renderPage()
    expect(await screen.findByText('via hermes-personal')).toBeInTheDocument()
  })

  it('offers only transitions the state machine allows', async () => {
    renderPage()
    await screen.findByText('Call dentist')

    const select = screen.getByLabelText('Change state of Call dentist')
    const options = Array.from(select.querySelectorAll('option'))
      .map((option) => option.getAttribute('value'))
      .filter(Boolean)

    // From CAPTURED the machine permits exactly these.
    expect(options.sort()).toEqual(
      ['BLOCKED', 'CANCELLED', 'PLANNED', 'READY'].sort(),
    )
    expect(options).not.toContain('COMPLETED')
  })

  it('offers no transitions from a terminal state', async () => {
    mockedTasks.list.mockResolvedValue({
      tasks: [makeTask({ state: 'COMPLETED' })],
      total: 1,
      by_state: { COMPLETED: 1 },
    })
    renderPage()
    // The Completed filter is needed because the default view hides closed work.
    await userEvent.click(await screen.findByRole('button', { name: 'Completed' }))

    expect(await screen.findByText('Call dentist')).toBeInTheDocument()
    expect(
      screen.queryByLabelText('Change state of Call dentist'),
    ).not.toBeInTheDocument()
  })

  it('surfaces the server reason when a transition is refused', async () => {
    mockedTasks.update.mockRejectedValue(
      new LifeOpsError(
        'invalid_transition',
        'cannot move task from CAPTURED to COMPLETED',
        409,
      ),
    )
    renderPage()
    await screen.findByText('Call dentist')

    await userEvent.selectOptions(
      screen.getByLabelText('Change state of Call dentist'),
      'READY',
    )

    expect(
      await screen.findByText('cannot move task from CAPTURED to COMPLETED'),
    ).toBeInTheDocument()
  })

  it('captures a new task through LifeOps Core', async () => {
    mockedTasks.create.mockResolvedValue(makeTask({ title: 'Book electrician' }))
    renderPage()
    await screen.findByText('Call dentist')

    await userEvent.type(screen.getByLabelText('New task title'), 'Book electrician')
    await userEvent.click(screen.getByRole('button', { name: /capture/i }))

    await waitFor(() =>
      expect(mockedTasks.create).toHaveBeenCalledWith({ title: 'Book electrician' }),
    )
  })

  it('flags tasks that cannot complete without evidence', async () => {
    mockedTasks.list.mockResolvedValue({
      tasks: [makeTask({ verification_required: true })],
      total: 1,
      by_state: { CAPTURED: 1 },
    })
    renderPage()
    expect(await screen.findByText('verification required')).toBeInTheDocument()
  })

  it('explains an unreachable LifeOps Core rather than showing a bare error', async () => {
    mockedTasks.list.mockRejectedValue(new Error('Network Error'))
    renderPage()
    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument()
  })
})
