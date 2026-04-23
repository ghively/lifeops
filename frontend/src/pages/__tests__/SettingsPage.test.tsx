import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SettingsPage } from '../SettingsPage'
import { settingsApi, agentRuntimeApi } from '@/services/api'

// Mock the API surfaces SettingsPage uses. The page queries:
//   settingsApi.get / settingsApi.getWatchedFolders
//   agentRuntimeApi.listMCPServers
// and mutates via settingsApi.update, settingsApi.addWatchedFolder,
// settingsApi.removeWatchedFolder, settingsApi.triggerBackup,
// agentRuntimeApi.createMCPServer/deleteMCPServer/etc.
vi.mock('@/services/api', () => ({
  settingsApi: {
    get: vi.fn(),
    update: vi.fn(),
    getWatchedFolders: vi.fn(),
    addWatchedFolder: vi.fn(),
    removeWatchedFolder: vi.fn(),
    triggerBackup: vi.fn(),
  },
  agentRuntimeApi: {
    listMCPServers: vi.fn(),
    createMCPServer: vi.fn(),
    deleteMCPServer: vi.fn(),
    connectMCPServer: vi.fn(),
    disconnectMCPServer: vi.fn(),
    testMCPServer: vi.fn(),
  },
}))

vi.mock('@/hooks/useToast', () => ({
  useToast: () => ({
    toast: vi.fn(),
    toasts: [],
    dismiss: vi.fn(),
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
        queries: { retry: false, gcTime: 0, staleTime: 0 },
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
    mockSettingsApi.getWatchedFolders.mockResolvedValue({ folders: [] })
    mockAgentRuntimeApi.listMCPServers.mockResolvedValue({ servers: [] })
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

  it('renders settings page heading', async () => {
    renderPage()

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /Settings/i, level: 1 })).toBeInTheDocument()
    })
  })

  it('displays loading spinner before settings resolve', async () => {
    mockSettingsApi.get.mockImplementation(
      () => new Promise((resolve) => {
        setTimeout(() => resolve({
          openclaw_url: 'http://localhost:18789',
          openclaw_token: '',
          openclaw_enabled: false,
          backup_snapshots: true,
          backup_markdown: true,
          backup_git: false,
          auto_index: true,
        }), 50)
      })
    )

    const { container } = renderPage()

    // While loading, the page shows an animated spinner instead of content.
    await waitFor(() => {
      expect(container.querySelector('.animate-spin')).toBeInTheDocument()
    })
  })

  it('displays OpenClaw integration section', async () => {
    renderPage()

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /OpenClaw Integration/i })).toBeInTheDocument()
    })
  })

  it('updates OpenClaw settings and calls update', async () => {
    const user = userEvent.setup()
    mockSettingsApi.update.mockResolvedValue({})

    renderPage()

    const urlInput = await screen.findByDisplayValue('http://localhost:18789')
    await user.clear(urlInput)
    await user.type(urlInput, 'http://new-url:18789')

    const saveButton = await screen.findByRole('button', { name: /save changes/i })
    await user.click(saveButton)

    await waitFor(() => {
      expect(mockSettingsApi.update).toHaveBeenCalled()
    })
  })

  it('can toggle a backup setting and save', async () => {
    const user = userEvent.setup()
    mockSettingsApi.update.mockResolvedValue({})

    renderPage()

    // Wait for render
    await screen.findByDisplayValue('http://localhost:18789')

    const checkboxes = screen.queryAllByRole('checkbox')
    if (checkboxes.length > 0) {
      await user.click(checkboxes[0])
    }

    const saveButton = await screen.findByRole('button', { name: /save changes/i })
    await user.click(saveButton)

    await waitFor(() => {
      expect(mockSettingsApi.update).toHaveBeenCalled()
    })
  })

  it('invokes update even when update API rejects', async () => {
    const user = userEvent.setup()
    mockSettingsApi.update.mockRejectedValue(new Error('Update failed'))

    renderPage()

    await screen.findByDisplayValue('http://localhost:18789')

    const saveButton = await screen.findByRole('button', { name: /save changes/i })
    await user.click(saveButton)

    await waitFor(() => {
      expect(mockSettingsApi.update).toHaveBeenCalled()
    })
  })

  it('displays watched folders section heading', async () => {
    renderPage()

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /Watched Folders/i })).toBeInTheDocument()
    })
  })

  it('displays MCP servers section heading', async () => {
    renderPage()

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /MCP/i })).toBeInTheDocument()
    })
  })

  it('renders with empty watched folders list', async () => {
    renderPage()

    await screen.findByRole('heading', { name: /Watched Folders/i })
    // Should render without errors; the list is simply empty.
    expect(mockSettingsApi.getWatchedFolders).toHaveBeenCalled()
  })

  it('fetches MCP servers on mount', async () => {
    renderPage()

    await waitFor(() => {
      expect(mockAgentRuntimeApi.listMCPServers).toHaveBeenCalled()
    })
  })

  it('allows clearing the OpenClaw URL input', async () => {
    const user = userEvent.setup()
    renderPage()

    const urlInput = (await screen.findByDisplayValue('http://localhost:18789')) as HTMLInputElement
    await user.clear(urlInput)

    expect(urlInput.value).toBe('')
  })

  it('disables save button while submitting', async () => {
    mockSettingsApi.update.mockImplementation(
      () => new Promise((resolve) => {
        setTimeout(() => resolve({}), 100)
      })
    )
    const user = userEvent.setup()
    renderPage()

    await screen.findByDisplayValue('http://localhost:18789')

    const saveButton = await screen.findByRole('button', { name: /save changes/i })
    await user.click(saveButton)

    await waitFor(() => {
      expect(saveButton).toBeDisabled()
    })
  })

  it('renders successfully after all queries resolve', async () => {
    renderPage()

    await waitFor(() => {
      expect(mockSettingsApi.get).toHaveBeenCalled()
      expect(mockSettingsApi.getWatchedFolders).toHaveBeenCalled()
      expect(mockAgentRuntimeApi.listMCPServers).toHaveBeenCalled()
    })

    // Heading is visible once settings resolve.
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /Settings/i, level: 1 })).toBeInTheDocument()
    })
  })
})
