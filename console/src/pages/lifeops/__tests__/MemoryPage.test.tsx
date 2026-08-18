/**
 * Memory screen behaviour (BUILD_SPEC section 17).
 *
 * The properties under test: memories render with provenance, search switches
 * the data source to /memory/search, correction supersedes rather than edits,
 * invalidation asks for a reason, and a server refusal is shown with the
 * server's own words.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { MemoryPage } from '../MemoryPage'
import {
  LifeOpsError,
  memoryApi,
  type MemoryRecord,
} from '@/services/lifeops'

vi.mock('@/services/lifeops', async () => {
  const actual = await vi.importActual<typeof import('@/services/lifeops')>(
    '@/services/lifeops',
  )
  return {
    ...actual,
    memoryApi: {
      list: vi.fn(),
      get: vi.fn(),
      search: vi.fn(),
      history: vi.fn(),
      remember: vi.fn(),
      invalidate: vi.fn(),
      correct: vi.fn(),
      promote: vi.fn(),
    },
  }
})

function makeMemory(overrides: Partial<MemoryRecord> = {}): MemoryRecord {
  return {
    id: 'mem_01abc',
    subject_id: 'person_gene',
    type: 'semantic',
    content: 'Favourite coffee is a flat white',
    source_type: 'conversation',
    source_id: 'session_42',
    observed_at: '2026-08-16T10:00:00Z',
    created_at: '2026-08-16T10:00:05Z',
    confidence: 0.9,
    importance: 0.6,
    valid_from: '2026-08-16T10:00:00Z',
    valid_to: null,
    supersedes: null,
    entity_ids: [],
    created_by_client: 'hermes-personal',
    invalidation_reason: null,
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
        <MemoryPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const mockedMemory = vi.mocked(memoryApi)

beforeEach(() => {
  mockedMemory.list.mockResolvedValue({
    memories: [makeMemory()],
    total: 1,
  })
  mockedMemory.search.mockResolvedValue({ memories: [], total: 0 })
  mockedMemory.history.mockResolvedValue({
    memory_id: 'mem_01abc',
    history: [makeMemory()],
    total: 1,
  })
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('Memory screen', () => {
  it('renders memories with their provenance summary', async () => {
    renderPage()
    expect(
      await screen.findByText('Favourite coffee is a flat white'),
    ).toBeInTheDocument()
    // The label appears on both the filter chip and the card's provenance row.
    expect(screen.getAllByText('Fact').length).toBeGreaterThanOrEqual(2)
    expect(screen.getAllByText('Conversation').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('confidence 0.90')).toBeInTheDocument()
  })

  it('filters by type through the API, not by hiding rows', async () => {
    renderPage()
    await screen.findByText('Favourite coffee is a flat white')

    await userEvent.click(screen.getByRole('button', { name: 'Episodic' }))

    await waitFor(() =>
      expect(mockedMemory.list).toHaveBeenCalledWith(
        expect.objectContaining({ type: ['episodic'] }),
      ),
    )
  })

  it('marks invalidated records instead of hiding them silently', async () => {
    mockedMemory.list.mockResolvedValue({
      memories: [
        makeMemory(),
        makeMemory({
          id: 'mem_04old',
          content: 'Favourite coffee is a latte',
          valid_to: '2026-08-15T09:00:00Z',
          invalidation_reason: 'taste changed',
        }),
      ],
      total: 2,
    })
    renderPage()
    expect(await screen.findByText('invalidated')).toBeInTheDocument()
  })

  it('searches through /memory/search when a query is typed', async () => {
    mockedMemory.search.mockResolvedValue({
      memories: [makeMemory({ content: 'Favourite coffee is a flat white' })],
      total: 1,
    })
    renderPage()
    await screen.findByText('Favourite coffee is a flat white')

    await userEvent.type(screen.getByLabelText('Search memories'), 'coffee')

    await waitFor(() =>
      expect(mockedMemory.search).toHaveBeenCalledWith('coffee', { limit: 50 }),
    )
  })

  it('filters the loaded list by source client-side', async () => {
    mockedMemory.list.mockResolvedValue({
      memories: [
        makeMemory(),
        makeMemory({
          id: 'mem_02def',
          content: 'Flight lands at 18:40 on Friday',
          source_type: 'email',
        }),
      ],
      total: 2,
    })
    renderPage()
    await screen.findByText('Flight lands at 18:40 on Friday')

    await userEvent.selectOptions(screen.getByLabelText('Filter by source'), 'email')

    expect(screen.getByText('Flight lands at 18:40 on Friday')).toBeInTheDocument()
    expect(
      screen.queryByText('Favourite coffee is a flat white'),
    ).not.toBeInTheDocument()
  })

  it('shows full provenance in the detail view', async () => {
    renderPage()
    await userEvent.click(
      await screen.findByText('Favourite coffee is a flat white'),
    )

    const detail = await screen.findByLabelText(
      'Memory detail: Favourite coffee is a flat white',
    )
    expect(detail).toHaveTextContent('session_42')
    expect(detail).toHaveTextContent('2026-08-16T10:00:00Z')
    expect(detail).toHaveTextContent('hermes-personal')
    expect(detail).toHaveTextContent('0.90 / 0.60')
  })

  it('renders the supersession chain in the detail view', async () => {
    mockedMemory.history.mockResolvedValue({
      memory_id: 'mem_01abc',
      history: [
        makeMemory(),
        makeMemory({
          id: 'mem_00old',
          content: 'Favourite coffee is a latte',
          valid_to: '2026-08-16T10:00:00Z',
        }),
      ],
      total: 2,
    })
    renderPage()
    await userEvent.click(
      await screen.findByText('Favourite coffee is a flat white'),
    )

    expect(await screen.findByText('Favourite coffee is a latte')).toBeInTheDocument()
    expect(mockedMemory.history).toHaveBeenCalledWith('mem_01abc')
  })

  it('corrects by superseding, never by editing in place', async () => {
    const corrected = makeMemory({
      id: 'mem_03new',
      content: 'Favourite coffee is now a cortado',
      supersedes: 'mem_01abc',
    })
    mockedMemory.correct.mockResolvedValue(corrected)
    renderPage()
    await userEvent.click(
      await screen.findByText('Favourite coffee is a flat white'),
    )
    await userEvent.click(screen.getByRole('button', { name: /correct/i }))

    const input = screen.getByLabelText('Corrected memory content')
    await userEvent.clear(input)
    await userEvent.type(input, 'Favourite coffee is now a cortado')
    await userEvent.click(screen.getByRole('button', { name: /save correction/i }))

    await waitFor(() =>
      expect(mockedMemory.correct).toHaveBeenCalledWith(
        'mem_01abc',
        'Favourite coffee is now a cortado',
      ),
    )
  })

  it('invalidates only with a reason', async () => {
    mockedMemory.invalidate.mockResolvedValue(
      makeMemory({ valid_to: '2026-08-16T11:00:00Z', invalidation_reason: 'outdated' }),
    )
    renderPage()
    await userEvent.click(
      await screen.findByText('Favourite coffee is a flat white'),
    )
    await userEvent.click(screen.getByRole('button', { name: /invalidate/i }))

    // The submit stays disabled until a reason exists — a reasonless
    // invalidation would destroy the audit trail (section 45).
    expect(
      screen.getByRole('button', { name: 'Invalidate', exact: true }),
    ).toBeDisabled()

    await userEvent.type(screen.getByLabelText('Invalidation reason'), 'outdated')
    await userEvent.click(screen.getByRole('button', { name: 'Invalidate', exact: true }))

    await waitFor(() =>
      expect(mockedMemory.invalidate).toHaveBeenCalledWith('mem_01abc', 'outdated'),
    )
  })

  it('surfaces the server reason when a correction is refused', async () => {
    mockedMemory.correct.mockRejectedValue(
      new LifeOpsError(
        'validation_error',
        'memory content looks like a secret; secrets belong in the SecretStore and are never stored as memory',
        422,
      ),
    )
    renderPage()
    await userEvent.click(
      await screen.findByText('Favourite coffee is a flat white'),
    )
    await userEvent.click(screen.getByRole('button', { name: /correct/i }))
    await userEvent.click(screen.getByRole('button', { name: /save correction/i }))

    expect(await screen.findByText(/never stored as memory/)).toBeInTheDocument()
  })

  it('explains an unreachable LifeOps Core rather than showing a bare error', async () => {
    mockedMemory.list.mockRejectedValue(new Error('Network Error'))
    renderPage()
    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument()
  })

  it('only offers promotion for a preference_candidate', async () => {
    renderPage()
    await userEvent.click(
      await screen.findByText('Favourite coffee is a flat white'),
    )
    expect(
      screen.queryByRole('button', { name: /promote to preference/i }),
    ).not.toBeInTheDocument()
  })

  it('promotes a candidate to a real preference with a human-supplied key', async () => {
    const candidate = makeMemory({
      id: 'mem_05cand',
      type: 'preference_candidate',
      content: 'nothing before ten',
    })
    mockedMemory.list.mockResolvedValue({ memories: [candidate], total: 1 })
    mockedMemory.history.mockResolvedValue({
      memory_id: 'mem_05cand',
      history: [candidate],
      total: 1,
    })
    mockedMemory.promote.mockResolvedValue({
      id: 'pref_01',
      key: 'scheduling.earliest_appointment_time',
      value: 'nothing before ten',
      subject_id: 'person_gene',
      source_type: 'user_explicit',
      confidence: 1,
      importance: 0.5,
      valid_from: '2026-08-16T10:00:00Z',
      created_at: '2026-08-16T10:00:00Z',
    } as never)
    mockedMemory.get.mockResolvedValue(
      makeMemory({
        ...candidate,
        valid_to: '2026-08-16T11:00:00Z',
        invalidation_reason: 'promoted to preference scheduling.earliest_appointment_time',
      }),
    )

    renderPage()
    await userEvent.click(await screen.findByText('nothing before ten'))
    await userEvent.click(
      screen.getByRole('button', { name: /promote to preference/i }),
    )

    const submit = screen.getByRole('button', { name: 'Promote', exact: true })
    expect(submit).toBeDisabled()

    await userEvent.type(
      screen.getByLabelText('Preference key'),
      'scheduling.earliest_appointment_time',
    )
    await userEvent.click(submit)

    await waitFor(() =>
      expect(mockedMemory.promote).toHaveBeenCalledWith(
        'mem_05cand',
        'scheduling.earliest_appointment_time',
        'nothing before ten',
      ),
    )
  })
})
