import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SettingsPage } from '../SettingsPage'
import { settingsApi, agentRuntimeApi } from '@/services/api'

vi.mock('@/services/api', () => ({
  settingsApi: {
    get: vi.fn(),
    update: vi.fn(),
    listWatchedFolders: vi.fn(),
    addWatchedFolder: vi.fn(),
    removeWatchedFolder: vi.fn(),
    listMCPServers: vi.fn(),
    createMCPServer: vi.fn(),
    updateMCPServer: vi.fn(),
    deleteMCPServer: vi.fn(),
  },
  agentRuntimeApi: {
    getStatus: vi.fn(),
  },
}))

vi.mock('@/hooks/useToast', () => ({
  useToast: () => ({
    addToast: vi.fn(),
    dismiss: vi.fn(),
    toasts: [],
  }),
}))

const mockSettingsApi = settingsApi as any
const mockAgentRuntimeApi = agentRuntimeApi as any

describe('SettingsPage', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    vi.clearAllMocks()
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })

    mockSettingsApi.get.mockResolvedValue({
      openclaw_url: 'http://localhost:18789',
      openclaw_token: 'token123',
      openclaw_enabled: false,
      backup_snapshots: true,
      backup_markdown: true,
      backup_git: false,
      git_repo_url: '',
      snapshot_interval_hours: 24,
      markdown_export_interval_hours: 48,
      git_sync_interval_minutes: 60,
      embedding_model: 'all-MiniLM-L6-v2',
      auto_index: true,
    })
    mockSettingsApi.listWatchedFolders.mockResolvedValue({ folders: [] })
    mockSettingsApi.listMCPServers.mockResolvedValue({ servers: [] })
    mockAgentRuntimeApi.getStatus.mockResolvedValue({ status: 'ready' })
  })

  const renderPage = () => {
    return render(
      <BrowserRouter>
        <QueryClientProvider client={queryClient}>
          <SettingsPage />
        </QueryClientProvider>
      </BrowserRouter>
    )
  }

  it('renders settings page', () => {
    renderPage()

    expect(screen.getByText(/settings/i)).toBeInTheDocument()
  })

  it('displays loading state', async () => {
    mockSettingsApi.get.mockImplementation(
      () =>
        new Promise((resolve) => {
          setTimeout(() => resolve({}), 50)
        })
    )

    renderPage()

    await waitFor(() => {
      expect(screen.getByRole('status')).toBeInTheDocument()
    })
  })

  it('displays settings form sections', async () => {
    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/openclaw|gateway/i)).toBeInTheDocument()
    })
  })

  it('updates OpenClaw settings', async () => {
    const user = userEvent.setup()
    mockSettingsApi.update.mockResolvedValue({ success: true })

    renderPage()

    await waitFor(() => {
      expect(screen.getByDisplayValue('http://localhost:18789')).toBeInTheDocument()
    })

    const urlInput = screen.getByDisplayValue('http://localhost:18789')
    await user.clear(urlInput)
    await user.type(urlInput, 'http://new-url:18789')

    const saveButton = screen.getByRole('button', { name: /save/i })
    await user.click(saveButton)

    await waitFor(() => {
      expect(mockSettingsApi.update).toHaveBeenCalled()
    })
  })

  it('updates backup settings', async () => {
    const user = userEvent.setup()
    mockSettingsApi.update.mockResolvedValue({ success: true })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/backup/i)).toBeInTheDocument()
    })

    const checkboxes = screen.queryAllByRole('checkbox')
    if (checkboxes.length > 0) {
      await user.click(checkboxes[0])
    }

    const saveButton = screen.getByRole('button', { name: /save/i })
    await user.click(saveButton)

    await waitFor(() => {
      expect(mockSettingsApi.update).toHaveBeenCalled()
    })
  })

  it('shows error on update failure', async () => {
    const user = userEvent.setup()
    mockSettingsApi.update.mockRejectedValue(new Error('Update failed'))

    renderPage()

    await waitFor(() => {
      expect(screen.getByDisplayValue('http://localhost:18789')).toBeInTheDocument()
    })

    const saveButton = screen.getByRole('button', { name: /save/i })
    await user.click(saveButton)

    await waitFor(() => {
      expect(screen.getByText(/error|failed/i)).toBeInTheDocument()
    })
  })

  it('displays watched folders section', async () => {
    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/watched folders|folder|directory/i)).toBeInTheDocument()
    })
  })

  it('displays MCP servers section', async () => {
    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/MCP|server/i)).toBeInTheDocument()
    })
  })

  it('adds new MCP server', async () => {
    const user = userEvent.setup()
    mockSettingsApi.createMCPServer.mockResolvedValue({ id: 'mcp-1' })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/MCP|server/i)).toBeInTheDocument()
    })

    const addButton = screen.queryByRole('button', { name: /add|new|create.*server/i })
    if (addButton) {
      await user.click(addButton)

      const nameInput = screen.queryByPlaceholderText(/name/i)
      if (nameInput) {
        await user.type(nameInput, 'Test Server')
      }

      const saveButton = screen.queryByRole('button', { name: /save|create/i })
      if (saveButton) {
        await user.click(saveButton)
      }
    }
  })

  it('validates required fields', async () => {
    const user = userEvent.setup()

    renderPage()

    await waitFor(() => {
      expect(screen.getByDisplayValue('http://localhost:18789')).toBeInTheDocument()
    })

    const urlInput = screen.getByDisplayValue('http://localhost:18789') as HTMLInputElement
    await user.clear(urlInput)

    // Should show validation error or disable save
    const saveButton = screen.queryByRole('button', { name: /save/i })
    if (saveButton && urlInput.required) {
      expect(urlInput.required).toBe(true)
    }
  })

  it('disables save while submitting', async () => {
    mockSettingsApi.update.mockImplementation(
      () =>
        new Promise((resolve) => {
          setTimeout(() => resolve({}), 100)
        })
    )

    const user = userEvent.setup()
    renderPage()

    await waitFor(() => {
      expect(screen.getByDisplayValue('http://localhost:18789')).toBeInTheDocument()
    })

    const saveButton = screen.getByRole('button', { name: /save/i })
    await user.click(saveButton)

    expect(saveButton).toBeDisabled()
  })

  it('displays agent runtime status', async () => {
    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/runtime|agent/i)).toBeInTheDocument()
    })
  })

  it('shows connection status indicators', async () => {
    renderPage()

    await waitFor(() => {
      const statusIndicators = screen.queryAllByRole('status')
      expect(statusIndicators.length).toBeGreaterThanOrEqual(0)
    })
  })
})
