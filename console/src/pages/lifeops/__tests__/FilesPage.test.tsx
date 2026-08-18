/**
 * Files screen behaviour (BUILD_SPEC sections 18, 36, 64, 96).
 *
 * A Document is a reference — title, source, a source-system id, a summary —
 * never a file upload, since LifeOps Core has no binary storage.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { FilesPage } from '../FilesPage'
import { LifeOpsError, documentsApi, type LifeOpsDocument } from '@/services/lifeops'

vi.mock('@/services/lifeops', async () => {
  const actual = await vi.importActual<typeof import('@/services/lifeops')>(
    '@/services/lifeops',
  )
  return {
    ...actual,
    documentsApi: {
      search: vi.fn(),
      get: vi.fn(),
      create: vi.fn(),
    },
  }
})

function makeDocument(overrides: Partial<LifeOpsDocument> = {}): LifeOpsDocument {
  return {
    id: 'document_01abc',
    title: 'ABC Electric quote',
    source: 'email',
    source_ref: 'msg-123',
    mime_type: '',
    summary: 'Quote for panel upgrade: $2,400',
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
        <FilesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const mockedDocuments = vi.mocked(documentsApi)

beforeEach(() => {
  mockedDocuments.search.mockResolvedValue({ documents: [makeDocument()], total: 1 })
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('Files', () => {
  it('lists recorded document references', async () => {
    renderPage()
    expect(await screen.findByText('ABC Electric quote')).toBeInTheDocument()
    expect(screen.getByText('Email')).toBeInTheDocument()
    expect(
      screen.getByText('Quote for panel upgrade: $2,400'),
    ).toBeInTheDocument()
  })

  it('searches as the query changes', async () => {
    renderPage()
    await screen.findByText('ABC Electric quote')

    await userEvent.type(screen.getByLabelText('Search files'), 'furnace')

    await waitFor(() =>
      expect(mockedDocuments.search).toHaveBeenCalledWith(
        expect.objectContaining({ q: 'furnace' }),
      ),
    )
  })

  it('opens the add form and records a new reference, never a file upload', async () => {
    mockedDocuments.create.mockResolvedValue(
      makeDocument({ id: 'document_02', title: 'Trash pickup notice', source: 'manual' }),
    )
    renderPage()
    await screen.findByText('ABC Electric quote')

    await userEvent.click(screen.getByRole('button', { name: /add reference/i }))
    await userEvent.type(screen.getByLabelText('Document title'), 'Trash pickup notice')

    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() =>
      expect(mockedDocuments.create).toHaveBeenCalledWith(
        expect.objectContaining({ title: 'Trash pickup notice', source: 'manual' }),
      ),
    )
    // No file input exists anywhere on the screen — this is a reference, not an upload.
    expect(document.querySelector('input[type="file"]')).not.toBeInTheDocument()
  })

  it('submits the selected source', async () => {
    mockedDocuments.create.mockResolvedValue(makeDocument({ id: 'document_03' }))
    renderPage()
    await screen.findByText('ABC Electric quote')

    await userEvent.click(screen.getByRole('button', { name: /add reference/i }))
    await userEvent.type(screen.getByLabelText('Document title'), 'Furnace warranty')
    await userEvent.selectOptions(screen.getByLabelText('Document source'), 'calendar')
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() =>
      expect(mockedDocuments.create).toHaveBeenCalledWith(
        expect.objectContaining({ source: 'calendar' }),
      ),
    )
  })

  it('surfaces a failed save instead of silently doing nothing', async () => {
    mockedDocuments.create.mockRejectedValue(
      new LifeOpsError('validation_error', 'Title is required.', 422),
    )
    renderPage()
    await screen.findByText('ABC Electric quote')

    await userEvent.click(screen.getByRole('button', { name: /add reference/i }))
    await userEvent.type(screen.getByLabelText('Document title'), 'Something')
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))

    expect(await screen.findByText('Title is required.')).toBeInTheDocument()
  })

  it('has an honest empty state', async () => {
    mockedDocuments.search.mockResolvedValue({ documents: [], total: 0 })
    renderPage()
    expect(
      await screen.findByText('No file references recorded yet.'),
    ).toBeInTheDocument()
  })

  it('explains an unreachable LifeOps Core rather than showing a bare error', async () => {
    mockedDocuments.search.mockRejectedValue(new Error('Network Error'))
    renderPage()
    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument()
  })
})
