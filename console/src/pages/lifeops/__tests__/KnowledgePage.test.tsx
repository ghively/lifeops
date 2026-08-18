/**
 * Knowledge screen behaviour (BUILD_SPEC sections 18, 36, 50).
 *
 * Reference notes distinct from Memory and Documents — search matches
 * title, category, and body text, and recording one is a Console act.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { KnowledgePage } from '../KnowledgePage'
import { LifeOpsError, knowledgeApi, type Knowledge } from '@/services/lifeops'

vi.mock('@/services/lifeops', async () => {
  const actual = await vi.importActual<typeof import('@/services/lifeops')>(
    '@/services/lifeops',
  )
  return {
    ...actual,
    knowledgeApi: {
      search: vi.fn(),
      get: vi.fn(),
      create: vi.fn(),
    },
  }
})

function makeKnowledge(overrides: Partial<Knowledge> = {}): Knowledge {
  return {
    id: 'knowledge_01abc',
    title: 'Water heater warranty',
    category: 'warranty',
    content: '10-year tank warranty, registered 2024.',
    source_document_id: null,
    created_at: '2026-08-17T10:00:00Z',
    updated_at: '2026-08-17T10:00:00Z',
    created_by_client: 'lifeops-console',
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
        <KnowledgePage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const mockedKnowledge = vi.mocked(knowledgeApi)

beforeEach(() => {
  mockedKnowledge.search.mockResolvedValue({ knowledge: [makeKnowledge()], total: 1 })
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('Knowledge', () => {
  it('lists recorded knowledge', async () => {
    renderPage()
    expect(await screen.findByText('Water heater warranty')).toBeInTheDocument()
    expect(screen.getByText('warranty')).toBeInTheDocument()
    expect(
      screen.getByText('10-year tank warranty, registered 2024.'),
    ).toBeInTheDocument()
  })

  it('searches as the query changes', async () => {
    renderPage()
    await screen.findByText('Water heater warranty')

    await userEvent.type(screen.getByLabelText('Search knowledge'), 'trash')

    await waitFor(() =>
      expect(mockedKnowledge.search).toHaveBeenCalledWith(
        expect.objectContaining({ q: 'trash' }),
      ),
    )
  })

  it('opens the add form and records a new entry', async () => {
    mockedKnowledge.create.mockResolvedValue(makeKnowledge({ id: 'knowledge_02', title: 'Trash day' }))
    renderPage()
    await screen.findByText('Water heater warranty')

    await userEvent.click(screen.getByRole('button', { name: /^add$/i }))
    await userEvent.type(screen.getByLabelText('Knowledge title'), 'Trash day')
    await userEvent.type(screen.getByLabelText('Knowledge content'), 'Tuesdays')

    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() =>
      expect(mockedKnowledge.create).toHaveBeenCalledWith(
        expect.objectContaining({ title: 'Trash day', content: 'Tuesdays' }),
      ),
    )
  })

  it('surfaces a failed save instead of silently doing nothing', async () => {
    mockedKnowledge.create.mockRejectedValue(
      new LifeOpsError('validation_error', 'Title is required.', 422),
    )
    renderPage()
    await screen.findByText('Water heater warranty')

    await userEvent.click(screen.getByRole('button', { name: /^add$/i }))
    await userEvent.type(screen.getByLabelText('Knowledge title'), 'Something')
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))

    expect(await screen.findByText('Title is required.')).toBeInTheDocument()
  })

  it('has an honest empty state', async () => {
    mockedKnowledge.search.mockResolvedValue({ knowledge: [], total: 0 })
    renderPage()
    expect(await screen.findByText('No knowledge recorded yet.')).toBeInTheDocument()
  })

  it('has an honest no-match state for a search', async () => {
    mockedKnowledge.search.mockResolvedValue({ knowledge: [], total: 0 })
    renderPage()
    await userEvent.type(screen.getByLabelText('Search knowledge'), 'nonexistent')
    expect(
      await screen.findByText('No knowledge matches “nonexistent”.'),
    ).toBeInTheDocument()
  })

  it('explains an unreachable LifeOps Core rather than showing a bare error', async () => {
    mockedKnowledge.search.mockRejectedValue(new Error('Network Error'))
    renderPage()
    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument()
  })
})
