/**
 * Approval screen behaviour (BUILD_SPEC section 58).
 *
 * The screen renders exactly what LifeOps Core attached to the approval —
 * the exact payload, the target, the amount — and submits Approve/Decline
 * without ever deciding for itself whether approval was needed.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApprovalsPage } from '../ApprovalsPage'
import { approvalsApi, type Approval } from '@/services/lifeops'

vi.mock('@/services/lifeops', async () => {
  const actual = await vi.importActual<typeof import('@/services/lifeops')>(
    '@/services/lifeops',
  )
  return {
    ...actual,
    approvalsApi: {
      listPending: vi.fn(),
      decide: vi.fn(),
    },
  }
})

function makeApproval(overrides: Partial<Approval> = {}): Approval {
  return {
    id: 'approval_01abc',
    action_id: 'action_01abc',
    payload_hash: 'deadbeef',
    requested_by: 'hermes-personal',
    approved_by: null,
    approved_at: null,
    expires_at: '2026-08-17T09:30:00Z',
    consumed_at: null,
    status: 'pending',
    action_type: 'book_appointment',
    authorises_action: 'Book appointment',
    does_not_authorise: ['Authorize repair work', 'Authorize additional charges'],
    target_entity_id: 'provider_abc_electric',
    amount: '89',
    created_at: '2026-08-17T09:00:00Z',
    action_payload: { time: 'Thursday 1-3 PM', amount: '89' },
    action_status: 'needs_approval',
    ...overrides,
  }
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <ApprovalsPage />
    </QueryClientProvider>,
  )
}

const mockedApprovals = vi.mocked(approvalsApi)

beforeEach(() => {
  mockedApprovals.listPending.mockResolvedValue({
    approvals: [makeApproval()],
    total: 1,
  })
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('Approvals', () => {
  it('asks LifeOps for pending approvals', async () => {
    renderPage()
    expect((await screen.findAllByText('provider_abc_electric'))[0]).toBeInTheDocument()
    expect(mockedApprovals.listPending).toHaveBeenCalledWith({ limit: 200 })
  })

  it('shows what will happen from the exact payload the server attached', async () => {
    renderPage()
    await screen.findAllByText('provider_abc_electric')
    expect(screen.getByText('Thursday 1-3 PM')).toBeInTheDocument()
    expect(screen.getAllByText('89').length).toBeGreaterThan(0)
  })

  it('shows what Hermes may and may not do, from the server', async () => {
    // Section 58's mockup lists specific exclusions, and section 101 step 9 is
    // "never authorize repairs". The Console must render the boundary the
    // domain enforces rather than composing a generic disclaimer of its own.
    renderPage()
    await screen.findAllByText('provider_abc_electric')
    expect(screen.getByText('Book appointment')).toBeInTheDocument()
    expect(screen.getByText('Authorize repair work')).toBeInTheDocument()
    expect(screen.getByText('Authorize additional charges')).toBeInTheDocument()
    expect(screen.getByText('Anything other than this exact request')).toBeInTheDocument()
  })

  it('renders no exclusions when the domain declares none', async () => {
    mockedApprovals.listPending.mockResolvedValue({
      approvals: [makeApproval({ does_not_authorise: [] })],
      total: 1,
    })
    renderPage()
    await screen.findAllByText('provider_abc_electric')
    expect(screen.queryByText('Authorize repair work')).not.toBeInTheDocument()
  })

  it('submits an approval decision without deciding anything itself', async () => {
    mockedApprovals.decide.mockResolvedValue(makeApproval({ status: 'approved' }))
    renderPage()
    await screen.findAllByText('provider_abc_electric')

    await userEvent.click(screen.getByRole('button', { name: /approve/i }))

    await waitFor(() =>
      expect(mockedApprovals.decide).toHaveBeenCalledWith('approval_01abc', true),
    )
  })

  it('submits a decline decision', async () => {
    mockedApprovals.decide.mockResolvedValue(makeApproval({ status: 'declined' }))
    renderPage()
    await screen.findAllByText('provider_abc_electric')

    await userEvent.click(screen.getByRole('button', { name: /decline/i }))

    await waitFor(() =>
      expect(mockedApprovals.decide).toHaveBeenCalledWith('approval_01abc', false),
    )
  })

  it('has an honest empty state', async () => {
    mockedApprovals.listPending.mockResolvedValue({ approvals: [], total: 0 })
    renderPage()
    expect(
      await screen.findByText('Nothing is waiting on your approval.'),
    ).toBeInTheDocument()
  })

  it('explains an unreachable LifeOps Core rather than showing a bare error', async () => {
    mockedApprovals.listPending.mockRejectedValue(new Error('Network Error'))
    renderPage()
    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument()
  })
})
