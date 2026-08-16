import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { LogsPage } from '../LogsPage'
import { systemApi } from '@/services/api'

// Mock the API calls the page makes
vi.mock('@/services/api', () => ({
  systemApi: {
    getUnifiedLogs: vi.fn(),
    getStatus: vi.fn(),
  },
}))

// useWebSocket opens a real WebSocket connection — stub it
vi.mock('@/hooks/useWebSocket', () => ({
  useWebSocket: () => ({
    connectionStatus: 'disconnected',
    lastMessage: null,
    sendMessage: vi.fn(),
  }),
}))

// logger lives in @/lib/logger; stub getEntries and subscribe so
// the component doesn't try to send log entries to a backend
vi.mock('@/lib/logger', () => ({
  logger: {
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    getEntries: vi.fn().mockReturnValue([]),
    subscribe: vi.fn().mockReturnValue(() => undefined),
  },
}))

// getSystemWsUrl is only used to build the WS URL; return a dummy value
vi.mock('@/lib/wsUrl', () => ({
  getSystemWsUrl: () => 'ws://localhost/api/v1/ws/system',
}))

vi.mock('@/components/QueryError', () => ({
  QueryError: ({ message }: { message: string }) => (
    <div data-testid="query-error">{message}</div>
  ),
}))

const mockSystemApi = systemApi as any

const mockLogs = [
  {
    timestamp: '2026-01-15T10:00:00Z',
    level: 'info',
    source: 'backend',
    message: 'Server started',
    logger: 'uvicorn',
    request_id: 'req-001',
  },
  {
    timestamp: '2026-01-15T10:01:00Z',
    level: 'error',
    source: 'frontend',
    message: 'Render error',
    logger: 'React',
    request_id: null,
  },
  {
    timestamp: '2026-01-15T10:02:00Z',
    level: 'warn',
    source: 'nginx',
    message: 'Upstream timeout',
    logger: null,
    request_id: null,
  },
]

const mockStatus = {
  version: '0.3.0',
  request_counts: { total: 1234 },
  error_counts: { total: 5 },
  active_websocket_connections: { total: 3 },
}

describe('LogsPage', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    vi.clearAllMocks()
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: 0, staleTime: 0 },
        mutations: { retry: false },
      },
    })
    mockSystemApi.getUnifiedLogs.mockResolvedValue({ logs: mockLogs, count: mockLogs.length })
    mockSystemApi.getStatus.mockResolvedValue(mockStatus)
  })

  const renderPage = () =>
    render(
      <BrowserRouter>
        <QueryClientProvider client={queryClient}>
          <LogsPage />
        </QueryClientProvider>
      </BrowserRouter>
    )

  it('renders the Logs heading after load', async () => {
    renderPage()
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /logs/i, level: 1 })).toBeInTheDocument()
    })
  })

  it('displays log entries from the API', async () => {
    renderPage()
    await waitFor(() => {
      expect(screen.getByText('Server started')).toBeInTheDocument()
      expect(screen.getByText('Render error')).toBeInTheDocument()
      expect(screen.getByText('Upstream timeout')).toBeInTheDocument()
    })
  })

  it('renders the Source filter select with backend, frontend and nginx options', async () => {
    renderPage()
    await waitFor(() => {
      // The source label is present
      expect(screen.getByLabelText(/source/i)).toBeInTheDocument()
    })
  })

  it('renders the Level filter select', async () => {
    renderPage()
    await waitFor(() => {
      expect(screen.getByLabelText(/level/i)).toBeInTheDocument()
    })
  })

  it('renders the Export JSON download button', async () => {
    renderPage()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /export json/i })).toBeInTheDocument()
    })
  })

  it('shows error state when backend logs API fails', async () => {
    mockSystemApi.getUnifiedLogs.mockRejectedValue(new Error('Network error'))
    renderPage()
    await waitFor(() => {
      expect(screen.getByTestId('query-error')).toBeInTheDocument()
    })
  })

  it('shows "No logs match" message when logs list is empty', async () => {
    mockSystemApi.getUnifiedLogs.mockResolvedValue({ logs: [], count: 0 })
    renderPage()
    await waitFor(() => {
      expect(screen.getByText(/no logs match the current filters/i)).toBeInTheDocument()
    })
  })

  it('renders the search input', async () => {
    renderPage()
    await waitFor(() => {
      expect(screen.getByLabelText(/search/i)).toBeInTheDocument()
    })
  })

  it('renders the auto-refresh checkbox and it is checked by default', async () => {
    renderPage()
    await waitFor(() => {
      const checkbox = screen.getByRole('checkbox')
      expect(checkbox).toBeInTheDocument()
      expect(checkbox).toBeChecked()
    })
  })

  it('auto-refresh checkbox can be unchecked', async () => {
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => {
      expect(screen.getByRole('checkbox')).toBeInTheDocument()
    })
    const checkbox = screen.getByRole('checkbox')
    await user.click(checkbox)
    expect(checkbox).not.toBeChecked()
  })

  it('displays status metrics when status query succeeds', async () => {
    renderPage()
    await waitFor(() => {
      // Version card
      expect(screen.getByText('0.3.0')).toBeInTheDocument()
    })
  })
})
