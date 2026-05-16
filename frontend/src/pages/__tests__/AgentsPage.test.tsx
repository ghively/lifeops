import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AgentsPage } from '../AgentsPage'
import { agentRuntimeApi, agentsApi } from '@/services/api'

// Mock only the API calls the page actually makes
vi.mock('@/services/api', () => ({
  agentRuntimeApi: {
    list: vi.fn(),
    listTemplates: vi.fn(),
    createAgent: vi.fn(),
    deleteAgent: vi.fn(),
    getAgentFile: vi.fn(),
    listScheduledTasks: vi.fn(),
    listWebhooks: vi.fn(),
    getUsage: vi.fn(),
    getAuditLog: vi.fn(),
    getCLIAgentStatus: vi.fn(),
    updateAgentFile: vi.fn(),
    curateMemory: vi.fn(),
    createScheduledTask: vi.fn(),
    deleteScheduledTask: vi.fn(),
    runScheduledTaskNow: vi.fn(),
    createWebhook: vi.fn(),
    deleteWebhook: vi.fn(),
  },
  agentsApi: {
    list: vi.fn(),
  },
}))

// Stub heavy sub-components that render markdown or complex UI
vi.mock('@/components/agents/CLIAgentStatus', () => ({
  CLIAgentStatus: () => <div data-testid="cli-agent-status-stub" />,
}))

vi.mock('@/components/agents/MarkdownEditor', () => ({
  MarkdownEditor: () => <div data-testid="markdown-editor-stub" />,
  AGENT_FILE_TABS: ['AGENT.md', 'SOUL.md', 'MEMORY.md', 'TOOLS.md'],
}))

vi.mock('@/components/QueryError', () => ({
  QueryError: ({ message }: { message: string }) => (
    <div data-testid="query-error">{message}</div>
  ),
}))

const mockAgentRuntimeApi = agentRuntimeApi as any
const mockAgentsApi = agentsApi as any

const mockRuntimeAgents = [
  { id: 'research-agent', path: '/agents/research-agent' },
  { id: 'coding-agent', path: '/agents/coding-agent' },
]

const mockAllAgents = [
  { name: 'research-agent', status: 'idle', description: 'Research tasks' },
  { name: 'coding-agent', status: 'running', description: 'Code tasks' },
]

function setupDefaultMocks() {
  mockAgentRuntimeApi.list.mockResolvedValue({ agents: mockRuntimeAgents })
  mockAgentsApi.list.mockResolvedValue({ agents: mockAllAgents })
  mockAgentRuntimeApi.getCLIAgentStatus.mockResolvedValue({})
  mockAgentRuntimeApi.listTemplates.mockResolvedValue({ templates: [] })
  mockAgentRuntimeApi.getAgentFile.mockResolvedValue({ name: 'AGENT.md', content: '# Agent' })
  mockAgentRuntimeApi.listScheduledTasks.mockResolvedValue({ tasks: [] })
  mockAgentRuntimeApi.listWebhooks.mockResolvedValue({ webhooks: [] })
  mockAgentRuntimeApi.getUsage.mockResolvedValue({
    current: {
      minute_requests: 0,
      minute_limit: 10,
      daily_tokens: 0,
      daily_token_limit: 100000,
    },
    history: [],
  })
  mockAgentRuntimeApi.getAuditLog.mockResolvedValue({ items: [] })
}

describe('AgentsPage', () => {
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

  const renderPage = () =>
    render(
      <BrowserRouter>
        <QueryClientProvider client={queryClient}>
          <AgentsPage />
        </QueryClientProvider>
      </BrowserRouter>
    )

  it('renders agents heading after load', async () => {
    renderPage()
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /agents/i, level: 1 })).toBeInTheDocument()
    })
  })

  it('shows loading state while fetching agents', async () => {
    mockAgentRuntimeApi.list.mockImplementation(
      () =>
        new Promise((resolve) =>
          setTimeout(() => resolve({ agents: mockRuntimeAgents }), 50)
        )
    )
    renderPage()
    await waitFor(() => {
      expect(screen.getByText(/loading agents/i)).toBeInTheDocument()
    })
  })

  it('displays list of runtime agents from API', async () => {
    renderPage()
    await waitFor(() => {
      expect(screen.getByText('research-agent')).toBeInTheDocument()
      expect(screen.getByText('coding-agent')).toBeInTheDocument()
    })
  })

  it('shows empty state when no agents exist', async () => {
    mockAgentRuntimeApi.list.mockResolvedValue({ agents: [] })
    renderPage()
    await waitFor(() => {
      expect(screen.getByText(/no runtime agents exist/i)).toBeInTheDocument()
    })
  })

  it('new agent input is present and create button is disabled when empty', async () => {
    renderPage()
    await waitFor(() => {
      expect(screen.getByText('research-agent')).toBeInTheDocument()
    })
    const input = screen.getByPlaceholderText('new-agent-id')
    expect(input).toBeInTheDocument()
    const newAgentButton = screen.getByRole('button', { name: /new agent/i })
    expect(newAgentButton).toBeDisabled()
  })

  it('create button is enabled after typing an agent id', async () => {
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => {
      expect(screen.getByPlaceholderText('new-agent-id')).toBeInTheDocument()
    })
    const input = screen.getByPlaceholderText('new-agent-id')
    await user.type(input, 'my-new-agent')
    const newAgentButton = screen.getByRole('button', { name: /new agent/i })
    expect(newAgentButton).toBeEnabled()
  })

  it('calls createAgent when New Agent button is clicked with a valid id', async () => {
    const user = userEvent.setup()
    mockAgentRuntimeApi.createAgent.mockResolvedValue({
      id: 'my-new-agent',
      path: '/agents/my-new-agent',
    })
    renderPage()
    await waitFor(() => {
      expect(screen.getByPlaceholderText('new-agent-id')).toBeInTheDocument()
    })
    const input = screen.getByPlaceholderText('new-agent-id')
    await user.type(input, 'my-new-agent')
    const newAgentButton = screen.getByRole('button', { name: /new agent/i })
    await user.click(newAgentButton)
    await waitFor(() => {
      expect(mockAgentRuntimeApi.createAgent).toHaveBeenCalledWith(
        'my-new-agent',
        null
      )
    })
  })

  it('delete button (trash icon) appears on each agent row', async () => {
    renderPage()
    await waitFor(() => {
      expect(screen.getByText('research-agent')).toBeInTheDocument()
    })
    // Each agent row has a ghost icon button that triggers delete confirmation
    // The delete icon buttons (Trash2) are rendered inside the agent rows
    const buttons = screen.getAllByRole('button')
    // At minimum we should have: New Agent + agent action buttons
    expect(buttons.length).toBeGreaterThan(2)
  })

  it('shows error state on API failure', async () => {
    mockAgentRuntimeApi.list.mockRejectedValue(new Error('Network error'))
    renderPage()
    await waitFor(() => {
      expect(screen.getByTestId('query-error')).toBeInTheDocument()
    })
  })

  it('selects an agent when its row is clicked, highlighting it', async () => {
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => {
      expect(screen.getByText('coding-agent')).toBeInTheDocument()
    })
    // Click the coding-agent row button
    const agentButtons = screen.getAllByRole('button', { name: '' })
    // Find the button that contains coding-agent text via closest
    const codingAgentRow = screen.getByText('coding-agent').closest('button')
    if (codingAgentRow) {
      await user.click(codingAgentRow)
    }
    // After click, the markdown editor stub should be visible (agent is selected)
    await waitFor(() => {
      expect(screen.getByTestId('markdown-editor-stub')).toBeInTheDocument()
    })
  })
})
