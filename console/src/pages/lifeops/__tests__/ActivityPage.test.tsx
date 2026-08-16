/**
 * Activity screen behaviour (BUILD_SPEC section 21).
 *
 * The feed is human-readable and newest-first, and it is labelled ephemeral:
 * the durable audit trail is Phase 4, and the screen must not pretend
 * otherwise.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ActivityPage } from '../ActivityPage'
import { systemApi, type ActivityEntry } from '@/services/lifeops'

vi.mock('@/services/lifeops', async () => {
  const actual = await vi.importActual<typeof import('@/services/lifeops')>(
    '@/services/lifeops',
  )
  return {
    ...actual,
    systemApi: {
      status: vi.fn(),
      health: vi.fn(),
      getActivity: vi.fn(),
    },
  }
})

function makeEntry(overrides: Partial<ActivityEntry> = {}): ActivityEntry {
  return {
    ts: '2026-08-16T10:32:00Z',
    operation: 'memory.search',
    result: 'ok',
    duration_ms: 12.4,
    client_id: 'hermes-personal',
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
        <ActivityPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const mockedSystem = vi.mocked(systemApi)

beforeEach(() => {
  mockedSystem.getActivity.mockResolvedValue([makeEntry()])
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('Activity', () => {
  it('renders recent activity from LifeOps Core', async () => {
    renderPage()
    expect(await screen.findByText('memory.search')).toBeInTheDocument()
    expect(screen.getByText('hermes-personal')).toBeInTheDocument()
    expect(screen.getByText('12 ms')).toBeInTheDocument()
  })

  it('shows newest entries first regardless of buffer order', async () => {
    mockedSystem.getActivity.mockResolvedValue([
      makeEntry({ operation: 'task.create', ts: '2026-08-16T10:32:00Z' }),
      makeEntry({ operation: 'preference.save', ts: '2026-08-16T10:38:00Z' }),
    ])
    renderPage()

    const earlier = await screen.findByText('task.create')
    const later = screen.getByText('preference.save')
    // `later` must come before `earlier` in document order.
    expect(
      later.compareDocumentPosition(earlier) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
  })

  it('flags a failed operation instead of hiding it', async () => {
    mockedSystem.getActivity.mockResolvedValue([
      makeEntry({ operation: 'task.transition', result: 'error' }),
    ])
    renderPage()
    const result = await screen.findByText('error')
    expect(result).toHaveClass('text-red-600')
  })

  it('shows the entity an entry touched when it carries one', async () => {
    mockedSystem.getActivity.mockResolvedValue([
      makeEntry({ task_id: 'task_01xyz' }),
    ])
    renderPage()
    expect(await screen.findByText('task_01xyz')).toBeInTheDocument()
  })

  it('is labelled as ephemeral recent activity, not durable audit', async () => {
    renderPage()
    expect(await screen.findByText('Ephemeral recent activity')).toBeInTheDocument()
    expect(screen.getByText(/durable audit trail arrives in Phase 4/i)).toBeInTheDocument()
  })

  it('has an honest empty state', async () => {
    mockedSystem.getActivity.mockResolvedValue([])
    renderPage()
    expect(await screen.findByText('No recent activity.')).toBeInTheDocument()
  })

  it('explains an unreachable LifeOps Core rather than showing a bare error', async () => {
    mockedSystem.getActivity.mockRejectedValue(new Error('Network Error'))
    renderPage()
    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument()
  })
})
