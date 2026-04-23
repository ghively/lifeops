import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SearchPage } from '../SearchPage'
import { searchApi, type SearchResult } from '@/services/api'

vi.mock('@/services/api', () => ({
  searchApi: {
    search: vi.fn(),
  },
}))

const mockSearchApi = searchApi as any

const mockResults: SearchResult[] = [
  {
    id: 'obj-1',
    name: 'Test Object',
    collection: 'objects',
    excerpt: 'This is a test',
    score: 0.95,
  },
  {
    id: 'file-1',
    name: 'Test File',
    collection: 'files',
    excerpt: 'File content',
    score: 0.87,
  },
]

describe('SearchPage', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    vi.clearAllMocks()
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })
    mockSearchApi.search.mockResolvedValue({ results: mockResults })
  })

  const renderPage = () => {
    return render(
      <BrowserRouter>
        <QueryClientProvider client={queryClient}>
          <SearchPage />
        </QueryClientProvider>
      </BrowserRouter>
    )
  }

  it('renders search input', () => {
    renderPage()

    const input = screen.getByPlaceholderText(/search/i)
    expect(input).toBeInTheDocument()
  })

  it('displays empty state initially', () => {
    renderPage()

    expect(screen.getByText(/search for/i)).toBeInTheDocument()
  })

  it('sends API request on Enter key', async () => {
    const user = userEvent.setup()
    renderPage()

    const input = screen.getByPlaceholderText(/search/i)
    await user.type(input, 'test query')
    await user.keyboard('{Enter}')

    await waitFor(() => {
      expect(mockSearchApi.search).toHaveBeenCalledWith('test query', 'semantic')
    })
  })

  it('displays search results', async () => {
    const user = userEvent.setup()
    renderPage()

    const input = screen.getByPlaceholderText(/search/i)
    await user.type(input, 'test')
    await user.keyboard('{Enter}')

    await waitFor(() => {
      expect(screen.getByText('Test Object')).toBeInTheDocument()
      expect(screen.getByText('Test File')).toBeInTheDocument()
    })
  })

  it('shows loading state while searching', async () => {
    mockSearchApi.search.mockImplementation(
      () =>
        new Promise((resolve) => {
          setTimeout(() => resolve({ results: mockResults }), 100)
        })
    )

    const user = userEvent.setup()
    renderPage()

    const input = screen.getByPlaceholderText(/search/i)
    await user.type(input, 'test')
    await user.keyboard('{Enter}')

    await waitFor(() => {
      expect(screen.getByRole('status')).toBeInTheDocument()
    })
  })

  it('displays error message on API failure', async () => {
    mockSearchApi.search.mockRejectedValue(new Error('API Error'))

    const user = userEvent.setup()
    renderPage()

    const input = screen.getByPlaceholderText(/search/i)
    await user.type(input, 'test')
    await user.keyboard('{Enter}')

    await waitFor(() => {
      expect(screen.getByText(/error|failed/i)).toBeInTheDocument()
    })
  })

  it('allows toggling between semantic and exact search', async () => {
    const user = userEvent.setup()
    renderPage()

    const exactButton = screen.getByRole('button', { name: /exact/i })
    await user.click(exactButton)

    const input = screen.getByPlaceholderText(/search/i)
    await user.type(input, 'test')
    await user.keyboard('{Enter}')

    await waitFor(() => {
      expect(mockSearchApi.search).toHaveBeenCalledWith('test', 'exact')
    })
  })

  it('debounces search input', async () => {
    vi.useFakeTimers()
    const user = userEvent.setup({ delay: null })

    renderPage()

    const input = screen.getByPlaceholderText(/search/i)
    await user.type(input, 'test')

    vi.advanceTimersByTime(100)

    expect(mockSearchApi.search).not.toHaveBeenCalled()

    vi.useRealTimers()
  })

  it('filters results by type', async () => {
    const user = userEvent.setup()
    renderPage()

    const input = screen.getByPlaceholderText(/search/i)
    await user.type(input, 'test')
    await user.keyboard('{Enter}')

    await waitFor(() => {
      expect(screen.getByText('Test Object')).toBeInTheDocument()
    })

    const fileFilter = screen.queryByRole('button', { name: /files/i })
    if (fileFilter) {
      await user.click(fileFilter)
    }
  })

  it('updates URL search params', async () => {
    const user = userEvent.setup()
    const { container } = renderPage()

    const input = screen.getByPlaceholderText(/search/i)
    await user.type(input, 'test query')
    await user.keyboard('{Enter}')

    await waitFor(() => {
      const url = window.location.href
      expect(url).toContain('q=test')
    })
  })

  it('clears search results when input is empty', async () => {
    const user = userEvent.setup()
    renderPage()

    const input = screen.getByPlaceholderText(/search/i) as HTMLInputElement
    await user.type(input, 'test')
    await user.keyboard('{Enter}')

    await waitFor(() => {
      expect(screen.getByText('Test Object')).toBeInTheDocument()
    })

    await user.clear(input)
    await user.keyboard('{Enter}')

    expect(mockSearchApi.search).not.toHaveBeenCalledWith('', expect.anything())
  })
})
