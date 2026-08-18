/**
 * Activity screen behaviour (BUILD_SPEC sections 21, 62).
 *
 * Two sources, honestly labelled: the durable audit log (every surface,
 * survives restarts) and this process's finer-grained in-memory feed.
 *
 * Section 21 asks for a human-readable narrative first, with technical
 * detail (trace ID, client ID, tool, risk class, duration, action ID,
 * verification evidence) behind an expand action — what's under test here.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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
    intent: 'create_appointment_hold',
    tool: 'calendar',
    risk: 'R3',
    approval: null,
    action: 'action_01',
    target: null,
    result: 'held',
    verification: null,
    timestamp: '2026-08-16T10:30:00Z',
    trace_id: 'trace_xyz',
    details: {},
    ...overrides,
  }
}

function makeEntry(overrides: Partial<ActivityEntry> = {}): ActivityEntry {
  return {
    ts: '2026-08-16T10:32:00Z',
    operation: 'memory.recall',
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
  it('renders a human-readable narrative, not the raw operation name', async () => {
    renderPage()
    expect(await screen.findByText('Hermes searched memory.')).toBeInTheDocument()
    expect(screen.queryByText('memory.recall')).not.toBeInTheDocument()
  })

  it('narrates the durable audit log too, honestly labelled', async () => {
    renderPage()
    expect(
      await screen.findByText('Hermes held a calendar appointment.'),
    ).toBeInTheDocument()
    expect(screen.getByText('Audit log')).toBeInTheDocument()
    expect(screen.queryByText('create_appointment_hold')).not.toBeInTheDocument()
    // The live feed says what it cannot see, instead of implying coverage.
    expect(screen.getByText(/does not see the separately running MCP server/i)).toBeInTheDocument()
  })

  it('hides technical detail until expanded, then shows it', async () => {
    renderPage()
    const row = await screen.findByRole('button', {
      name: /show technical detail for: hermes held a calendar appointment/i,
    })

    expect(screen.queryByText('trace_xyz')).not.toBeInTheDocument()
    expect(screen.queryByText('action_01')).not.toBeInTheDocument()

    await userEvent.click(row)

    expect(screen.getByText('trace_xyz')).toBeInTheDocument()
    expect(screen.getByText('action_01')).toBeInTheDocument()
    expect(screen.getByText('R3')).toBeInTheDocument()

    await userEvent.click(row)
    expect(screen.queryByText('trace_xyz')).not.toBeInTheDocument()
  })

  it('falls back to a plain, still-readable line for an unmapped operation', async () => {
    mockedSystem.getActivity.mockResolvedValue([
      makeEntry({ operation: 'task.transition', result: 'ok' }),
    ])
    renderPage()
    expect(await screen.findByText('Hermes — Task transition (ok).')).toBeInTheDocument()
  })

  it('shows newest entries first regardless of buffer order', async () => {
    mockedSystem.getActivity.mockResolvedValue([
      makeEntry({ operation: 'task.create', ts: '2026-08-16T10:32:00Z' }),
      makeEntry({ operation: 'memory.recall', ts: '2026-08-16T10:38:00Z' }),
    ])
    renderPage()

    const earlier = await screen.findByText('Hermes created a task.')
    const later = screen.getByText('Hermes searched memory.')
    // `later` must come before `earlier` in document order.
    expect(
      later.compareDocumentPosition(earlier) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
  })

  it('flags a failed operation instead of hiding it', async () => {
    mockedSystem.getActivity.mockResolvedValue([
      makeEntry({ operation: 'task.create', result: 'error' }),
    ])
    renderPage()
    const narrative = await screen.findByText('Hermes created a task.')
    expect(narrative).toHaveClass('text-red-600')
  })

  it('shows the touched entity id behind the expand action', async () => {
    mockedSystem.getActivity.mockResolvedValue([
      makeEntry({ operation: 'task.create', task_id: 'task_01xyz' }),
    ])
    renderPage()
    const row = await screen.findByRole('button', {
      name: /show technical detail for: hermes created a task/i,
    })
    expect(screen.queryByText('task_01xyz')).not.toBeInTheDocument()
    await userEvent.click(row)
    expect(screen.getByText('task_01xyz')).toBeInTheDocument()
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
