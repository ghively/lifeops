/**
 * Needs Attention screen behaviour (BUILD_SPEC section 12).
 *
 * The screen asks LifeOps for exactly the attention states, explains why each
 * task stopped, and offers only transitions the state machine permits — a
 * refusal is shown verbatim, never hidden.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { NeedsAttentionPage } from '../NeedsAttentionPage'
import { LifeOpsError, systemApi, tasksApi, type Task, type TaskState } from '@/services/lifeops'

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
      ...actual.systemApi,
      getTransitions: vi.fn(),
    },
  }
})

// The page must follow the table the server serves, not a hardcoded copy, so
// this stand-in deliberately differs from the real state machine on an
// unrelated state (CAPTURED may only move to PLANNED or CANCELLED here).
const SERVER_TRANSITIONS: Record<TaskState, TaskState[]> = {
  CAPTURED: ['PLANNED', 'CANCELLED'],
  PLANNED: ['READY', 'CAPTURED', 'BLOCKED', 'CANCELLED'],
  READY: ['EXECUTING', 'PLANNED', 'BLOCKED', 'CANCELLED'],
  EXECUTING: [
    'WAITING_EXTERNAL',
    'NEEDS_APPROVAL',
    'VERIFYING',
    'COMPLETED',
    'BLOCKED',
    'FAILED',
    'CANCELLED',
  ],
  WAITING_EXTERNAL: [
    'EXECUTING',
    'NEEDS_APPROVAL',
    'VERIFYING',
    'BLOCKED',
    'FAILED',
    'CANCELLED',
  ],
  NEEDS_APPROVAL: ['EXECUTING', 'BLOCKED', 'FAILED', 'CANCELLED'],
  VERIFYING: ['COMPLETED', 'WAITING_EXTERNAL', 'BLOCKED', 'FAILED'],
  BLOCKED: ['READY', 'PLANNED', 'EXECUTING', 'FAILED', 'CANCELLED'],
  FAILED: ['READY', 'PLANNED', 'CANCELLED'],
  COMPLETED: [],
  CANCELLED: [],
}

function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task_01abc',
    title: 'Approve electrician booking',
    description: null,
    state: 'NEEDS_APPROVAL',
    priority: 'high',
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
    needs_attention: true,
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
        <NeedsAttentionPage />
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
    by_state: { NEEDS_APPROVAL: 1 },
  })
  mockedSystem.getTransitions.mockResolvedValue(SERVER_TRANSITIONS)
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('Needs Attention', () => {
  it('asks LifeOps for exactly the attention states', async () => {
    renderPage()
    expect(await screen.findByText('Approve electrician booking')).toBeInTheDocument()
    expect(mockedTasks.list).toHaveBeenCalledWith({
      state: ['NEEDS_APPROVAL', 'BLOCKED', 'FAILED'],
      limit: 200,
    })
  })

  it('groups tasks by why they need a human', async () => {
    mockedTasks.list.mockResolvedValue({
      tasks: [
        makeTask({ id: 'task_a', title: 'Approve booking' }),
        makeTask({ id: 'task_b', title: 'Resolve conflict', state: 'BLOCKED' }),
        makeTask({ id: 'task_c', title: 'Retry payment', state: 'FAILED' }),
      ],
      total: 3,
      by_state: { NEEDS_APPROVAL: 1, BLOCKED: 1, FAILED: 1 },
    })
    renderPage()

    expect(
      await screen.findByRole('heading', { name: 'Approval' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Conflict' })).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: 'Failed external action' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Resolve conflict')).toBeInTheDocument()
    expect(screen.getByText('Retry payment')).toBeInTheDocument()
  })

  it('recognises MFA, security, and price/term keywords over the default state grouping', async () => {
    mockedTasks.list.mockResolvedValue({
      tasks: [
        makeTask({
          id: 'task_mfa',
          title: 'Approve booking',
          state: 'BLOCKED',
          current_action: 'waiting for a one-time code from ABC Electric',
        }),
        makeTask({
          id: 'task_security',
          title: 'Suspicious login attempt flagged',
          state: 'NEEDS_APPROVAL',
        }),
        makeTask({
          id: 'task_price',
          title: 'Quote increased since last check',
          state: 'NEEDS_APPROVAL',
        }),
      ],
      total: 3,
      by_state: { BLOCKED: 1, NEEDS_APPROVAL: 2 },
    })
    renderPage()

    expect(await screen.findByRole('heading', { name: 'MFA' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Security warning' })).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: 'Price or term change' }),
    ).toBeInTheDocument()
    // These three would otherwise all land under one state-based heading —
    // the point of categorize() is that they don't.
    expect(screen.queryByRole('heading', { name: 'Approval' })).not.toBeInTheDocument()
  })

  it('says what the task was doing when it stopped', async () => {
    mockedTasks.list.mockResolvedValue({
      tasks: [
        makeTask({ current_action: 'booking Thursday 1–3 PM with ABC Electric' }),
      ],
      total: 1,
      by_state: { NEEDS_APPROVAL: 1 },
    })
    renderPage()
    expect(
      await screen.findByText('Approve: booking Thursday 1–3 PM with ABC Electric'),
    ).toBeInTheDocument()
  })

  it('offers only transitions the state machine allows', async () => {
    renderPage()
    await screen.findByText('Approve electrician booking')

    const select = screen.getByLabelText('Change state of Approve electrician booking')
    const options = Array.from(select.querySelectorAll('option'))
      .map((option) => option.getAttribute('value'))
      .filter(Boolean)

    // From NEEDS_APPROVAL the machine permits exactly these.
    expect(options.sort()).toEqual(
      ['BLOCKED', 'CANCELLED', 'EXECUTING', 'FAILED'].sort(),
    )
  })

  it('surfaces the server reason when a transition is refused', async () => {
    mockedTasks.update.mockRejectedValue(
      new LifeOpsError('not_permitted', 'client lifeops-console may not execute tasks', 403),
    )
    renderPage()
    await screen.findByText('Approve electrician booking')

    await userEvent.selectOptions(
      screen.getByLabelText('Change state of Approve electrician booking'),
      'EXECUTING',
    )

    expect(
      await screen.findByText('client lifeops-console may not execute tasks'),
    ).toBeInTheDocument()
  })

  it('treats an empty screen as good news, not a bug', async () => {
    mockedTasks.list.mockResolvedValue({ tasks: [], total: 0, by_state: {} })
    renderPage()
    expect(
      await screen.findByText('Nothing needs your attention right now.'),
    ).toBeInTheDocument()
  })

  it('explains an unreachable LifeOps Core rather than showing a bare error', async () => {
    mockedTasks.list.mockRejectedValue(new Error('Network Error'))
    renderPage()
    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument()
  })
})
