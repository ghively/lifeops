/**
 * Activity screen behaviour (BUILD_SPEC sections 21, 62).
 *
 * Two sources, honestly labelled: the durable audit log (every surface,
 * survives restarts) and this process's finer-grained in-memory feed.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ActivityPage } from '../ActivityPage'
import { auditApi, systemApi, type ActivityEntry, type AuditRecord } from '@/services/lifeops'

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
    auditApi: {
      read: vi.fn(),
    },
  }
})

function makeAuditRecord(overrides: Partial<AuditRecord> = {}): AuditRecord {
  return {
    id: 'audit_01',
    requester: null,
    user: null,
    client: 'hermes-personal',
    session: null,
    intent: 'book_appointment',
    tool: 'book_appointment',
    risk: 'R3',
    approval: null,
    action: 'action_01',
    target: null,
    result: 'prepared',
    verification: null,
    timestamp: '2026-08-16T10:30:00Z',
    trace_id: null,
    details: {},
    ...overrides,
  }
}

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
const mockedAudit = vi.mocked(auditApi)

beforeEach(() => {
  mockedSystem.getActivity.mockResolvedValue([makeEntry()])
  mockedAudit.read.mockResolvedValue({ records: [makeAuditRecord()], total: 1 })
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('Activity', () => {
  it('renders recent activity from LifeOps Core', async () => {
    renderPage()
    expect(await screen.findByText('memory.search')).toBeInTheDocument()
    expect(screen.getAllByText('hermes-personal').length).toBeGreaterThan(0)
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

  it('shows the durable audit log, honestly labelled', async () => {
    renderPage()
    expect(await screen.findByText('Audit log')).toBeInTheDocument()
    expect((await screen.findAllByText('book_appointment')).length).toBeGreaterThan(0)
    // The live feed says what it cannot see, instead of implying coverage.
    expect(screen.getByText(/does not see the separately running MCP server/i)).toBeInTheDocument()
  })

  it('has an honest empty state', async () => {
    mockedSystem.getActivity.mockResolvedValue([])
    mockedAudit.read.mockResolvedValue({ records: [], total: 0 })
    renderPage()
    expect(
      await screen.findByText('No recent activity in this process.'),
    ).toBeInTheDocument()
    expect(screen.getByText('Nothing recorded yet.')).toBeInTheDocument()
  })

  it('explains an unreachable LifeOps Core rather than showing a bare error', async () => {
    mockedSystem.getActivity.mockRejectedValue(new Error('Network Error'))
    mockedAudit.read.mockRejectedValue(new Error('Network Error'))
    renderPage()
    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument()
  })
})
