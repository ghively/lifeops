import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
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
    title: 'Test Object',
    collection: 'objects',
    content: 'This is a test',
    score: 0.95,
  } as any,
  {
    id: 'file-1',
    filename: 'Test File',
    collection: 'files',
    content: 'File content',
    score: 0.87,
  } as any,
]

describe('SearchPage', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    vi.clearAllMocks()
    // Reset URL so state from prior tests doesn't leak through BrowserRouter.
    window.history.replaceState(null, '', '/')
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: 0, staleTime: 0 },
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

    const input = screen.getByPlaceholderText(/Search across all your knowledge/i)
    expect(input).toBeInTheDocument()
  })

  it('displays empty-state prompt initially', () => {
    renderPage()

    expect(screen.getByText(/Start searching/i)).toBeInTheDocument()
  })

  it('sends API request on Enter key', async () => {
    const user = userEvent.setup()
    renderPage()

    const input = screen.getByPlaceholderText(/Search across all/i)
    await user.type(input, 'test query')
    await user.keyboard('{Enter}')

    await waitFor(() => {
      expect(mockSearchApi.search).toHaveBeenCalledWith('test query', 'semantic')
    })
  })

  it('displays search results', async () => {
    const user = userEvent.setup()
    renderPage()

    const input = screen.getByPlaceholderText(/Search across all/i)
    await user.type(input, 'test')
    await user.keyboard('{Enter}')

    await waitFor(() => {
      expect(screen.getByText('Test Object')).toBeInTheDocument()
      expect(screen.getByText('Test File')).toBeInTheDocument()
    })
  })

  it('shows loading spinner while searching', async () => {
    mockSearchApi.search.mockImplementation(
      () => new Promise((resolve) => {
        setTimeout(() => resolve({ results: mockResults }), 100)
      })
    )

    const user = userEvent.setup()
    const { container } = renderPage()

    const input = screen.getByPlaceholderText(/Search across all/i)
    await user.type(input, 'test')
    await user.keyboard('{Enter}')

    await waitFor(() => {
      expect(container.querySelector('.animate-spin')).toBeInTheDocument()
    })
  })

  it('displays error message on API failure', async () => {
    mockSearchApi.search.mockRejectedValue(new Error('API Error'))

    const user = userEvent.setup()
    renderPage()

    const input = screen.getByPlaceholderText(/Search across all/i)
    await user.type(input, 'test')
    await user.keyboard('{Enter}')

    await waitFor(() => {
      expect(screen.getByText(/API Error/i)).toBeInTheDocument()
    })
  })

  it('allows toggling between semantic and exact search', async () => {
    const user = userEvent.setup()
    renderPage()

    const exactButton = screen.getByRole('button', { name: /Exact Match/i })
    await user.click(exactButton)

    const input = screen.getByPlaceholderText(/Search across all/i)
    await user.type(input, 'test')
    await user.keyboard('{Enter}')

    await waitFor(() => {
      expect(mockSearchApi.search).toHaveBeenCalledWith('test', 'exact')
    })
  })

  it('does not search until Enter (no implicit debounce)', async () => {
    const user = userEvent.setup()
    renderPage()

    const input = screen.getByPlaceholderText(/Search across all/i)
    await user.type(input, 'test')

    // Typing alone should NOT trigger a search — SearchPage waits for Enter
    // or a click on the Search button. Small delay to rule out async fire.
    await new Promise((r) => setTimeout(r, 50))
    expect(mockSearchApi.search).not.toHaveBeenCalled()
  })

  it('shows result type label (files filter badge) when searching', async () => {
    const user = userEvent.setup()
    renderPage()

    const input = screen.getByPlaceholderText(/Search across all/i)
    await user.type(input, 'test')
    await user.keyboard('{Enter}')

    await waitFor(() => {
      expect(screen.getByText('Test Object')).toBeInTheDocument()
    })

    // Each result renders a capitalized collection badge
    const fileBadges = screen.queryAllByText(/files/i)
    expect(fileBadges.length).toBeGreaterThan(0)
  })

  it('updates URL search params after searching', async () => {
    const user = userEvent.setup()
    renderPage()

    const input = screen.getByPlaceholderText(/Search across all/i)
    await user.type(input, 'test query')
    await user.keyboard('{Enter}')

    await waitFor(() => {
      expect(window.location.search).toContain('q=test')
    })
  })

  it('does not search for empty string even after Enter', async () => {
    const user = userEvent.setup()
    renderPage()

    const input = screen.getByPlaceholderText(/Search across all/i) as HTMLInputElement
    await user.type(input, 'test')
    await user.keyboard('{Enter}')

    await waitFor(() => {
      expect(screen.getByText('Test Object')).toBeInTheDocument()
    })

    await user.clear(input)
    await user.keyboard('{Enter}')

    // Search should never have been called with empty string.
    const calls = mockSearchApi.search.mock.calls as Array<[string, string]>
    expect(calls.every(([q]) => q !== '')).toBe(true)
  })
})
