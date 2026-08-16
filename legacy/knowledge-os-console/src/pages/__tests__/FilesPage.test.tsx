import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { FilesPage } from '../FilesPage'
import { filesApi, settingsApi, type FileItem } from '@/services/api'

vi.mock('@/services/api', () => ({
  filesApi: {
    list: vi.fn(),
    reindex: vi.fn(),
  },
  settingsApi: {
    addWatchedFolder: vi.fn(),
  },
}))

vi.mock('@/components/QueryError', () => ({
  QueryError: ({ message }: { message: string }) => (
    <div data-testid="query-error">{message}</div>
  ),
}))

const mockFilesApi = filesApi as any
const mockSettingsApi = settingsApi as any

const mockFiles: FileItem[] = [
  {
    id: 'file-1',
    name: 'report.pdf',
    filename: 'report.pdf',
    path: '/home/user/documents/report.pdf',
    mime_type: 'application/pdf',
    content_type: 'application/pdf',
    size_bytes: 204800,
    index_status: 'indexed',
    last_indexed: '2026-01-15T10:00:00Z',
  } as FileItem,
  {
    id: 'file-2',
    name: 'script.py',
    filename: 'script.py',
    path: '/home/user/code/script.py',
    mime_type: 'text/x-python',
    content_type: 'text/x-python',
    size_bytes: 4096,
    index_status: 'processing',
    last_indexed: null,
  } as FileItem,
  {
    id: 'file-3',
    name: 'notes.md',
    filename: 'notes.md',
    path: '/home/user/notes/notes.md',
    mime_type: 'text/markdown',
    content_type: 'text/markdown',
    size_bytes: 1024,
    index_status: 'error',
    error_message: 'Parse error',
    last_indexed: null,
  } as FileItem,
]

describe('FilesPage', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    vi.clearAllMocks()
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: 0, staleTime: 0 },
        mutations: { retry: false },
      },
    })
    mockFilesApi.list.mockResolvedValue({ files: mockFiles })
    mockFilesApi.reindex.mockResolvedValue({})
    mockSettingsApi.addWatchedFolder.mockResolvedValue({})
  })

  const renderPage = () =>
    render(
      <BrowserRouter>
        <QueryClientProvider client={queryClient}>
          <FilesPage />
        </QueryClientProvider>
      </BrowserRouter>
    )

  it('renders Files heading after load', async () => {
    renderPage()
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /files/i, level: 1 })).toBeInTheDocument()
    })
  })

  it('shows loading spinner while fetching', async () => {
    mockFilesApi.list.mockImplementation(
      () =>
        new Promise((resolve) =>
          setTimeout(() => resolve({ files: mockFiles }), 50)
        )
    )
    const { container } = renderPage()
    await waitFor(() => {
      expect(container.querySelector('.animate-spin')).toBeInTheDocument()
    })
  })

  it('displays list of files from API', async () => {
    renderPage()
    await waitFor(() => {
      expect(screen.getByText('report.pdf')).toBeInTheDocument()
      expect(screen.getByText('script.py')).toBeInTheDocument()
      expect(screen.getByText('notes.md')).toBeInTheDocument()
    })
  })

  it('shows file size for indexed files', async () => {
    renderPage()
    await waitFor(() => {
      // 204800 bytes = 200.0 KB
      expect(screen.getByText('200.0 KB')).toBeInTheDocument()
    })
  })

  it('renders status filter buttons (all, indexed, processing, pending, error)', async () => {
    renderPage()
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /files/i })).toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: 'all' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'indexed' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'processing' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'pending' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'error' })).toBeInTheDocument()
  })

  it('clicking a status filter hides non-matching files', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('report.pdf')

    const indexedFilter = screen.getByRole('button', { name: 'indexed' })
    await user.click(indexedFilter)

    // Only indexed files should remain
    await waitFor(() => {
      expect(screen.getByText('report.pdf')).toBeInTheDocument()
      expect(screen.queryByText('script.py')).not.toBeInTheDocument()
    })
  })

  it('opens Add Folder dialog when Add Folder button is clicked', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByRole('heading', { name: /files/i })

    const addFolderButton = screen.getByRole('button', { name: /add folder/i })
    await user.click(addFolderButton)

    await waitFor(() => {
      expect(screen.getByText('Add Watched Folder')).toBeInTheDocument()
    })
  })

  it('shows empty state when no files match filter', async () => {
    mockFilesApi.list.mockResolvedValue({ files: [] })
    renderPage()
    await waitFor(() => {
      expect(screen.getByText(/no files found/i)).toBeInTheDocument()
    })
  })

  it('shows error state when API fails', async () => {
    mockFilesApi.list.mockRejectedValue(new Error('Failed to load files'))
    renderPage()
    await waitFor(() => {
      expect(screen.getByTestId('query-error')).toBeInTheDocument()
    })
  })

  it('file row shows the index_status badge', async () => {
    renderPage()
    await waitFor(() => {
      // indexed badge from report.pdf
      const badges = screen.getAllByText('indexed')
      expect(badges.length).toBeGreaterThan(0)
    })
  })
})
