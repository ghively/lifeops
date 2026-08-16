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
import {
  LifeOpsError,
  systemApi,
  tasksApi,
  type Task,
  type TaskState,
} from '@/services/lifeops'

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
    systemApi: {
      getTransitions: vi.fn(),
    },
  }
})

/**
 * The table the tests pretend the server returned. Deliberately differs from
 * any client-side copy: CAPTURED may only move to PLANNED or CANCELLED here,
 * which is how the tests prove the page follows the server, not a constant.
 */
const SERVER_TRANSITIONS: Record<TaskState, TaskState[]> = {
  CAPTURED: ['PLANNED', 'CANCELLED'],
  PLANNED: ['READY', 'CAPTURED', 'BLOCKED', 'CANCELLED'],
  READY: ['EXECUTING', 'PLANNED', 'BLOCKED', 'CANCELLED'],
  EXECUTING: ['COMPLETED', 'FAILED', 'CANCELLED'],
  WAITING_EXTERNAL: ['EXECUTING', 'FAILED', 'CANCELLED'],
  NEEDS_APPROVAL: ['EXECUTING', 'CANCELLED'],
  VERIFYING: ['COMPLETED', 'FAILED'],
  BLOCKED: ['READY', 'CANCELLED'],
  FAILED: ['READY', 'CANCELLED'],
  COMPLETED: [],
  CANCELLED: [],
}

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
const mockedSystem = vi.mocked(systemApi)

beforeEach(() => {
  mockedTasks.list.mockResolvedValue({
    tasks: [makeTask()],
    total: 1,
    by_state: { CAPTURED: 1 },
  })
  mockedSystem.getTransitions.mockResolvedValue(SERVER_TRANSITIONS)
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

  it('offers only transitions the server-served table allows', async () => {
    renderPage()
    await screen.findByText('Call dentist')

    const select = await screen.findByLabelText('Change state of Call dentist')
    const options = Array.from(select.querySelectorAll('option'))
      .map((option) => option.getAttribute('value'))
      .filter(Boolean)

    // The mocked server permits exactly these from CAPTURED — notably not
    // READY or BLOCKED, which a hardcoded client-side copy would have offered.
    expect(options.sort()).toEqual(['CANCELLED', 'PLANNED'])
    expect(options).not.toContain('READY')
    expect(options).not.toContain('COMPLETED')
    expect(mockedSystem.getTransitions).toHaveBeenCalled()
  })

  it('shows an honest loading state while transitions are fetched', async () => {
    mockedSystem.getTransitions.mockReturnValue(new Promise(() => {}))
    renderPage()
    await screen.findByText('Call dentist')

    expect(screen.getByText(/loading allowed transitions/i)).toBeInTheDocument()
    // No dropdown until the choices are known — guessing is worse than waiting.
    expect(
      screen.queryByLabelText('Change state of Call dentist'),
    ).not.toBeInTheDocument()
  })

  it('explains when transitions cannot be loaded and offers retry', async () => {
    mockedSystem.getTransitions.mockRejectedValueOnce(
      new LifeOpsError('internal', 'transition table unavailable', 500),
    )
    renderPage()
    await screen.findByText('Call dentist')

    expect(
      await screen.findByText(/could not load the allowed transitions/i),
    ).toBeInTheDocument()
    expect(screen.getByText(/transition table unavailable/)).toBeInTheDocument()
    expect(
      screen.queryByLabelText('Change state of Call dentist'),
    ).not.toBeInTheDocument()

    mockedSystem.getTransitions.mockResolvedValue(SERVER_TRANSITIONS)
    await userEvent.click(screen.getByRole('button', { name: /retry/i }))

    expect(
      await screen.findByLabelText('Change state of Call dentist'),
    ).toBeInTheDocument()
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
        'cannot move task from CAPTURED to PLANNED',
        409,
      ),
    )
    renderPage()
    await screen.findByText('Call dentist')

    await userEvent.selectOptions(
      await screen.findByLabelText('Change state of Call dentist'),
      'PLANNED',
    )

    expect(
      await screen.findByText('cannot move task from CAPTURED to PLANNED'),
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
