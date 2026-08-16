/**
 * Search screen behaviour (BUILD_SPEC section 19).
 *
 * Phase 1 searches people, preferences, and tasks through LifeOps Core and
 * groups the results. Only kinds with a screen link anywhere; the rest render
 * plainly rather than promising a screen that does not exist yet.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { SearchPage } from '../SearchPage'
import { searchApi, type Person, type Preference, type Task } from '@/services/lifeops'

vi.mock('@/services/lifeops', async () => {
  const actual = await vi.importActual<typeof import('@/services/lifeops')>(
    '@/services/lifeops',
  )
  return {
    ...actual,
    searchApi: { search: vi.fn() },
  }
})

function makePerson(overrides: Partial<Person> = {}): Person {
  return {
    id: 'person_gene',
    display_name: 'Gene Hively',
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
    subject_id: 'person_gene',
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
      screen.getByText('Search people, preferences, and tasks.'),
    ).toBeInTheDocument()
    expect(mockedSearch.search).not.toHaveBeenCalled()
  })

  it('searches LifeOps Core with the submitted query', async () => {
    mockedSearch.search.mockResolvedValue({ people: [], preferences: [], tasks: [] })
    renderPage()

    await userEvent.type(screen.getByLabelText('Search query'), 'electrician')
    await userEvent.click(screen.getByRole('button', { name: /search/i }))

    await waitFor(() =>
      expect(mockedSearch.search).toHaveBeenCalledWith('electrician'),
    )
  })

  it('groups results into people, preferences, and tasks', async () => {
    mockedSearch.search.mockResolvedValue({
      people: [makePerson({ aliases: ['Gene'] })],
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
    expect(screen.getByText('Gene Hively')).toBeInTheDocument()
    expect(screen.getByText('also known as Gene')).toBeInTheDocument()
    expect(screen.getByText('coffee')).toBeInTheDocument()
    expect(screen.getByText('black, no sugar')).toBeInTheDocument()
    expect(screen.getByText('Repair living room outlet')).toBeInTheDocument()
  })

  it('links task results to the Tasks screen', async () => {
    mockedSearch.search.mockResolvedValue({
      people: [],
      preferences: [],
      tasks: [makeTask()],
    })
    renderPage()

    await userEvent.type(screen.getByLabelText('Search query'), 'outlet')
    await userEvent.click(screen.getByRole('button', { name: /search/i }))

    const row = (await screen.findByText('Repair living room outlet')).closest('a')
    expect(row).toHaveAttribute('href', '/tasks')
  })

  it('omits groups with no results', async () => {
    mockedSearch.search.mockResolvedValue({
      people: [],
      preferences: [],
      tasks: [makeTask()],
    })
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
    mockedSearch.search.mockResolvedValue({ people: [], preferences: [], tasks: [] })
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
})
