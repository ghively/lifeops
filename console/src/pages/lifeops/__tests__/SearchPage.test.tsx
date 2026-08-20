/**
 * Search screen behaviour (BUILD_SPEC section 19).
 *
 * Searches all twelve of the section's categories through LifeOps Core and
 * groups the results. Only kinds with a screen link anywhere; the rest render
 * plainly rather than promising a screen that does not exist yet.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { SearchPage } from '../SearchPage'
import {
  searchApi,
  type Person,
  type Preference,
  type SearchResults,
  type Task,
} from '@/services/lifeops'

vi.mock('@/services/lifeops', async () => {
  const actual = await vi.importActual<typeof import('@/services/lifeops')>(
    '@/services/lifeops',
  )
  return {
    ...actual,
    searchApi: { search: vi.fn() },
  }
})

const EMPTY_RESULTS: SearchResults = {
  people: [],
  preferences: [],
  tasks: [],
  providers: [],
  assets: [],
  appointments: [],
  events: [],
  memories: [],
  documents: [],
  knowledge: [],
  bills: [],
  actions: [],
  historical_facts: [],
}

function makePerson(overrides: Partial<Person> = {}): Person {
  return {
    id: 'person_jordan',
    display_name: 'Jordan Blake',
    is_primary: true,
    aliases: [],
    timezone: 'America/Chicago',
    created_at: '2026-08-16T10:00:00Z',
    updated_at: '2026-08-16T10:00:00Z',
    ...overrides,
  }
}

function makePreference(overrides: Partial<Preference> = {}): Preference {
  return {
    id: 'pref_01',
    subject_id: 'person_jordan',
    key: 'coffee',
    value: 'black, no sugar',
    source_type: 'stated',
    source_id: null,
    confidence: 1,
    importance: 0.5,
    observed_at: '2026-08-16T10:00:00Z',
    created_at: '2026-08-16T10:00:00Z',
    valid_from: '2026-08-16T10:00:00Z',
    valid_to: null,
    supersedes: null,
    created_by_client: 'hermes-personal',
    notes: null,
    is_current: true,
    ...overrides,
  }
}

function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task_01abc',
    title: 'Repair living room outlet',
    description: null,
    state: 'CAPTURED',
    priority: 'medium',
    created_at: '2026-08-16T10:00:00Z',
    updated_at: '2026-08-16T10:00:00Z',
    due_at: null,
    owner_entity_id: 'person_jordan',
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
        <SearchPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const mockedSearch = vi.mocked(searchApi)

afterEach(() => {
  vi.clearAllMocks()
})

describe('Search', () => {
  it('does not search before the user asks', () => {
    renderPage()
    expect(
      screen.getByText(/Search people, preferences, tasks, providers/),
    ).toBeInTheDocument()
    expect(mockedSearch.search).not.toHaveBeenCalled()
  })

  it('searches LifeOps Core with the submitted query', async () => {
    mockedSearch.search.mockResolvedValue(EMPTY_RESULTS)
    renderPage()

    await userEvent.type(screen.getByLabelText('Search query'), 'electrician')
    await userEvent.click(screen.getByRole('button', { name: /search/i }))

    await waitFor(() =>
      expect(mockedSearch.search).toHaveBeenCalledWith('electrician'),
    )
  })

  it('groups results into people, preferences, and tasks', async () => {
    mockedSearch.search.mockResolvedValue({
      ...EMPTY_RESULTS,
      people: [makePerson({ aliases: ['Jordan'] })],
      preferences: [makePreference()],
      tasks: [makeTask()],
    })
    renderPage()

    await userEvent.type(screen.getByLabelText('Search query'), 'outlet')
    await userEvent.click(screen.getByRole('button', { name: /search/i }))

    expect(
      await screen.findByRole('heading', { name: 'People' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Preferences' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Tasks' })).toBeInTheDocument()
    expect(screen.getByText('Jordan Blake')).toBeInTheDocument()
    expect(screen.getByText('also known as Jordan')).toBeInTheDocument()
    expect(screen.getByText('coffee')).toBeInTheDocument()
    expect(screen.getByText('black, no sugar')).toBeInTheDocument()
    expect(screen.getByText('Repair living room outlet')).toBeInTheDocument()
  })

  it('links task results to the Tasks screen', async () => {
    mockedSearch.search.mockResolvedValue({ ...EMPTY_RESULTS, tasks: [makeTask()] })
    renderPage()

    await userEvent.type(screen.getByLabelText('Search query'), 'outlet')
    await userEvent.click(screen.getByRole('button', { name: /search/i }))

    const row = (await screen.findByText('Repair living room outlet')).closest('a')
    expect(row).toHaveAttribute('href', '/tasks')
  })

  it('omits groups with no results', async () => {
    mockedSearch.search.mockResolvedValue({ ...EMPTY_RESULTS, tasks: [makeTask()] })
    renderPage()

    await userEvent.type(screen.getByLabelText('Search query'), 'outlet')
    await userEvent.click(screen.getByRole('button', { name: /search/i }))

    await screen.findByRole('heading', { name: 'Tasks' })
    expect(screen.queryByRole('heading', { name: 'People' })).not.toBeInTheDocument()
    expect(
      screen.queryByRole('heading', { name: 'Preferences' }),
    ).not.toBeInTheDocument()
  })

  it('says so when nothing matches', async () => {
    mockedSearch.search.mockResolvedValue(EMPTY_RESULTS)
    renderPage()

    await userEvent.type(screen.getByLabelText('Search query'), 'platypus')
    await userEvent.click(screen.getByRole('button', { name: /search/i }))

    expect(await screen.findByText('No results for “platypus”.')).toBeInTheDocument()
  })

  it('explains an unreachable LifeOps Core rather than showing a bare error', async () => {
    mockedSearch.search.mockRejectedValue(new Error('Network Error'))
    renderPage()

    await userEvent.type(screen.getByLabelText('Search query'), 'outlet')
    await userEvent.click(screen.getByRole('button', { name: /search/i }))

    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument()
  })

  it('renders the widened categories the audit found missing', async () => {
    mockedSearch.search.mockResolvedValue({
      ...EMPTY_RESULTS,
      providers: [
        {
          id: 'provider_abc_electric',
          entity_type: 'provider',
          display_name: 'ABC Electric',
          facts: {},
          created_at: '2026-08-16T10:00:00Z',
          updated_at: '2026-08-16T10:00:00Z',
          created_by_client: null,
        },
      ],
      assets: [
        {
          id: 'asset_land_rover',
          entity_type: 'asset',
          display_name: 'Land Rover',
          facts: {},
          created_at: '2026-08-16T10:00:00Z',
          updated_at: '2026-08-16T10:00:00Z',
          created_by_client: null,
        },
      ],
      knowledge: [
        {
          id: 'knowledge_01',
          title: 'Water heater warranty',
          category: 'warranty',
          content: '10-year tank warranty',
          source_document_id: null,
          created_at: '2026-08-16T10:00:00Z',
          updated_at: '2026-08-16T10:00:00Z',
          created_by_client: null,
        },
      ],
      bills: [
        {
          id: 'bill_01',
          payee_id: 'payee_abc_electric',
          description: 'March invoice',
          amount: '89.10',
          currency: 'USD',
          due_at: null,
          status: 'pending',
          action_id: null,
          paid_at: null,
          external_reference: null,
          source_document_id: null,
          created_at: '2026-08-16T10:00:00Z',
          updated_at: '2026-08-16T10:00:00Z',
          created_by_client: null,
          is_payable: false,
        },
      ],
    })
    renderPage()

    await userEvent.type(screen.getByLabelText('Search query'), 'electric')
    await userEvent.click(screen.getByRole('button', { name: /search/i }))

    expect(await screen.findByRole('heading', { name: 'Providers' })).toBeInTheDocument()
    expect(screen.getByText('ABC Electric')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Assets' })).toBeInTheDocument()
    expect(screen.getByText('Land Rover')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Knowledge' })).toBeInTheDocument()
    expect(screen.getByText('Water heater warranty')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Bills' })).toBeInTheDocument()
    expect(screen.getByText('March invoice')).toBeInTheDocument()
  })

  it('renders events, actions, and historical facts — the last two categories', async () => {
    mockedSearch.search.mockResolvedValue({
      ...EMPTY_RESULTS,
      events: [
        {
          id: 'event_01',
          entity_type: 'event',
          display_name: 'Dentist follow-up',
          facts: {},
          created_at: '2026-08-16T10:00:00Z',
          updated_at: '2026-08-16T10:00:00Z',
          created_by_client: null,
        },
      ],
      actions: [
        {
          id: 'action_01',
          type: 'place_phone_call',
          status: 'executed',
          idempotency_key: 'idem_01',
          payload_hash: 'hash_01',
          payload: {},
          task_id: null,
          target_entity_id: 'provider_abc_electric',
          created_at: '2026-08-16T10:00:00Z',
          attempt_count: 1,
          last_attempt_at: '2026-08-16T10:00:00Z',
          external_reference: 'CA123',
          verification_state: 'verified',
          failure_reason: null,
          created_by_client: 'hermes-personal',
        },
      ],
      historical_facts: [
        {
          id: 'audit_01',
          requester: 'hermes-personal',
          user: 'person_jordan',
          client: 'hermes-personal',
          session: null,
          intent: 'place_phone_call',
          tool: 'place_phone_call',
          risk: 'R2',
          approval: null,
          action: 'action_01',
          target: 'provider_abc_electric',
          result: 'ok',
          verification: null,
          timestamp: '2026-08-16T10:00:00Z',
          trace_id: null,
          details: {},
        },
      ],
    })
    renderPage()

    await userEvent.type(screen.getByLabelText('Search query'), 'electric')
    await userEvent.click(screen.getByRole('button', { name: /search/i }))

    expect(await screen.findByRole('heading', { name: 'Events' })).toBeInTheDocument()
    expect(screen.getByText('Dentist follow-up')).toBeInTheDocument()

    expect(screen.getByRole('heading', { name: 'Actions' })).toBeInTheDocument()
    expect(screen.getByText('Place a phone call')).toBeInTheDocument()
    const actionRow = screen.getByText('Place a phone call').closest('a')
    expect(actionRow).toHaveAttribute('href', '/activity')

    expect(
      screen.getByRole('heading', { name: 'Historical facts' }),
    ).toBeInTheDocument()
    const factRow = screen.getByText('place_phone_call').closest('a')
    expect(factRow).toHaveAttribute('href', '/activity')
  })
})
