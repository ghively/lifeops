import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AgentChatPage } from '../AgentChatPage'
import { agentRuntimeApi, agentsApi } from '@/services/api'

vi.mock('@/services/api', () => ({
  agentRuntimeApi: {
    getAgentSessions: vi.fn(),
    getSessionMessages: vi.fn(),
    deleteSession: vi.fn(),
  },
  agentsApi: {
    list: vi.fn(),
  },
}))

// useAgentChat manages streaming — stub it so tests stay synchronous
vi.mock('@/hooks/useAgentChat', () => ({
  useAgentChat: () => ({
    messages: [],
    isStreaming: false,
    currentToolCall: null,
    error: null,
    activeSessionId: null,
    sendMessage: vi.fn(),
    resetMessages: vi.fn(),
  }),
}))

// useWebSocketStore requires a real WebSocket connection — stub it
vi.mock('@/stores/websocket', () => ({
  useWebSocketStore: (selector: (state: any) => any) =>
    selector({
      connect: vi.fn(),
      send: vi.fn(),
      isConnected: false,
      lastMessage: null,
    }),
}))

// ApprovalDialog is a controlled dialog, stub it to avoid portal issues
vi.mock('@/components/agents/ApprovalDialog', () => ({
  ApprovalDialog: () => null,
}))

// MarkdownRenderer uses react-markdown — stub it
vi.mock('@/components/agents/MarkdownRenderer', () => ({
  MarkdownRenderer: ({ content }: { content: string }) => (
    <div data-testid="markdown-renderer">{content}</div>
  ),
}))

const mockAgentRuntimeApi = agentRuntimeApi as any
const mockAgentsApi = agentsApi as any

const mockAgents = [
  { name: 'research-agent', status: 'idle', description: 'Research tasks' },
  { name: 'coding-agent', status: 'idle', description: 'Code tasks' },
]

const mockSessions = [
  {
    id: 'session-1',
    title: 'First session',
    updated_at: '2026-01-01T10:00:00Z',
    message_count: 5,
  },
  {
    id: 'session-2',
    title: 'Second session',
    updated_at: '2026-01-02T10:00:00Z',
    message_count: 3,
  },
]

function setupDefaultMocks() {
  mockAgentsApi.list.mockResolvedValue({ agents: mockAgents })
  mockAgentRuntimeApi.getAgentSessions.mockResolvedValue({ sessions: mockSessions })
  mockAgentRuntimeApi.getSessionMessages.mockResolvedValue({ messages: [] })
}

describe('AgentChatPage', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    vi.clearAllMocks()
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: 0, staleTime: 0 },
        mutations: { retry: false },
      },
    })
    setupDefaultMocks()
  })

  const renderPage = (agentId = 'research-agent') =>
    render(
      <MemoryRouter initialEntries={[`/agents/${agentId}/chat`]}>
        <Routes>
          <Route
            path="/agents/:id/chat"
            element={
              <QueryClientProvider client={queryClient}>
                <AgentChatPage />
              </QueryClientProvider>
            }
          />
        </Routes>
      </MemoryRouter>
    )

  it('renders Agent Chat heading', async () => {
    renderPage()
    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: /agent chat/i, level: 1 })
      ).toBeInTheDocument()
    })
  })

  it('shows session list from API', async () => {
    renderPage()
    await waitFor(() => {
      expect(screen.getByText('First session')).toBeInTheDocument()
      expect(screen.getByText('Second session')).toBeInTheDocument()
    })
  })

  it('renders the chat message input', async () => {
    renderPage()
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/message research-agent/i)).toBeInTheDocument()
    })
  })

  it('Send button is disabled when input is empty', async () => {
    renderPage()
    await waitFor(() => {
      const sendButton = screen.getByRole('button', { name: /send/i })
      expect(sendButton).toBeDisabled()
    })
  })

  it('Send button becomes enabled when text is typed', async () => {
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/message research-agent/i)).toBeInTheDocument()
    })
    const input = screen.getByPlaceholderText(/message research-agent/i)
    await user.type(input, 'Hello agent')
    expect(screen.getByRole('button', { name: /send/i })).toBeEnabled()
  })

  it('shows New Session button', async () => {
    renderPage()
    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: /new session/i })
      ).toBeInTheDocument()
    })
  })

  it('shows session error state when sessions fail to load', async () => {
    mockAgentRuntimeApi.getAgentSessions.mockRejectedValue(
      new Error('Failed to load sessions')
    )
    renderPage()
    await waitFor(() => {
      expect(screen.getByText(/failed to load sessions/i)).toBeInTheDocument()
    })
  })
})
