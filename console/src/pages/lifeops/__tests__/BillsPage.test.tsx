/**
 * Bills screen behaviour (BUILD_SPEC sections 72, 99).
 *
 * Pins the load-bearing rules: amounts render as the exact string the server
 * sent, a proposed payee shows as unapproved until approved, preparing a
 * payment never implies anything was paid, and settling requires a typed
 * confirmation reference.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { BillsPage } from '../BillsPage'
import { billsApi, payeesApi, type Bill, type Payee } from '@/services/lifeops'

vi.mock('@/services/lifeops', async () => {
  const actual = await vi.importActual<typeof import('@/services/lifeops')>(
    '@/services/lifeops',
  )
  return {
    ...actual,
    payeesApi: {
      list: vi.fn(),
      propose: vi.fn(),
      approve: vi.fn(),
    },
    billsApi: {
      list: vi.fn(),
      get: vi.fn(),
      record: vi.fn(),
      preparePayment: vi.fn(),
      settle: vi.fn(),
    },
  }
})

function makePayee(overrides: Partial<Payee> = {}): Payee {
  return {
    id: 'payee_utility_co',
    display_name: 'Utility Co',
    provider_entity_id: null,
    secret_ref: null,
    created_at: '2026-08-16T08:00:00Z',
    approved_at: '2026-08-16T09:00:00Z',
    approved_by: 'console',
    created_by_client: 'lifeops-console',
    is_approved: true,
    ...overrides,
  }
}

function makeBill(overrides: Partial<Bill> = {}): Bill {
  return {
    id: 'bill_01abc',
    payee_id: 'payee_utility_co',
    description: 'Electricity',
    amount: '89.10',
    currency: 'USD',
    due_at: '2026-08-20T00:00:00Z',
    status: 'due',
    action_id: null,
    paid_at: null,
    external_reference: null,
    source_document_id: null,
    created_at: '2026-08-16T08:00:00Z',
    updated_at: '2026-08-16T08:00:00Z',
    created_by_client: 'lifeops-console',
    is_payable: true,
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
        <BillsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const mockedPayees = vi.mocked(payeesApi)
const mockedBills = vi.mocked(billsApi)

beforeEach(() => {
  mockedPayees.list.mockResolvedValue({ payees: [makePayee()], total: 1 })
  mockedBills.list.mockResolvedValue({ bills: [makeBill()], total: 1 })
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('Bills', () => {
  it('renders the amount as the exact string the server sent', async () => {
    renderPage()
    expect(await screen.findByText('Electricity')).toBeInTheDocument()
    // Never "89.1" — a JS number would have dropped the trailing zero.
    expect(screen.getByText('89.10 USD')).toBeInTheDocument()
  })

  it('shows an approved payee as usable', async () => {
    renderPage()
    await screen.findByText('Electricity')
    expect(
      screen.getByText('Approved — bills may be paid to this payee'),
    ).toBeInTheDocument()
  })

  it('shows an unapproved payee as not yet payable, on both the payee and the bill', async () => {
    mockedPayees.list.mockResolvedValue({
      payees: [makePayee({ approved_at: null, approved_by: null, is_approved: false })],
      total: 1,
    })
    renderPage()
    await screen.findByText('Electricity')
    expect(screen.getByText('Awaiting approval — cannot be paid yet')).toBeInTheDocument()
    expect(screen.getByText('payee not yet approved')).toBeInTheDocument()
  })

  it('proposing a payee submits a proposal, not a usable payee', async () => {
    mockedPayees.propose.mockResolvedValue({ action_id: 'action_1', status: 'needs_approval' })
    renderPage()
    await screen.findByText('Electricity')

    await userEvent.click(screen.getByRole('button', { name: /propose payee/i }))
    await userEvent.type(screen.getByLabelText('Name'), 'City Water')
    await userEvent.click(screen.getByRole('button', { name: /^propose$/i }))

    await waitFor(() =>
      expect(mockedPayees.propose).toHaveBeenCalledWith({
        display_name: 'City Water',
        provider_entity_id: undefined,
      }),
    )
  })

  it('approving a payee submits the decision', async () => {
    mockedPayees.list.mockResolvedValue({
      payees: [makePayee({ approved_at: null, approved_by: null, is_approved: false })],
      total: 1,
    })
    mockedPayees.approve.mockResolvedValue(makePayee())
    renderPage()
    await screen.findByText('Electricity')

    await userEvent.click(screen.getByRole('button', { name: /^approve$/i }))

    await waitFor(() => expect(mockedPayees.approve).toHaveBeenCalledWith('payee_utility_co'))
  })

  it('preparing a payment never implies anything was paid, and points at Approvals', async () => {
    mockedBills.preparePayment.mockResolvedValue({
      action_id: 'action_1',
      status: 'needs_approval',
    })
    renderPage()
    await screen.findByText('Electricity')

    await userEvent.click(screen.getByRole('button', { name: /prepare payment/i }))

    await waitFor(() => expect(mockedBills.preparePayment).toHaveBeenCalledWith('bill_01abc'))
    expect(
      await screen.findByText(/needs your approval before anything is sent/i),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /go to approvals/i })).toHaveAttribute(
      'href',
      '/approvals',
    )
  })

  it('settling requires a typed confirmation reference', async () => {
    renderPage()
    await screen.findByText('Electricity')

    // Opens the dialog. Its own submit button reads "Settle" too, so both
    // the row action and the dialog submit match — the dialog's is last.
    await userEvent.click(screen.getByRole('button', { name: /^settle$/i }))
    const dialogSubmit = () => screen.getAllByRole('button', { name: /^settle$/i }).at(-1)!

    // No reference typed yet: the submit button stays disabled.
    expect(dialogSubmit()).toBeDisabled()

    mockedBills.settle.mockResolvedValue(makeBill({ status: 'paid', external_reference: 'CONF-9' }))
    await userEvent.type(screen.getByLabelText('Confirmation reference'), 'CONF-9')
    await userEvent.click(dialogSubmit())

    await waitFor(() =>
      expect(mockedBills.settle).toHaveBeenCalledWith('bill_01abc', 'CONF-9'),
    )
  })

  it('has an honest empty state', async () => {
    mockedPayees.list.mockResolvedValue({ payees: [], total: 0 })
    mockedBills.list.mockResolvedValue({ bills: [], total: 0 })
    renderPage()
    expect(await screen.findByText('No payees yet.')).toBeInTheDocument()
    expect(screen.getByText('Nothing recorded yet.')).toBeInTheDocument()
  })

  it('explains an unreachable LifeOps Core rather than showing a bare error', async () => {
    mockedPayees.list.mockRejectedValue(new Error('Network Error'))
    renderPage()
    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument()
  })
})
