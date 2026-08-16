/**
 * System screen behaviour (BUILD_SPEC section 77).
 *
 * The screen reports what LifeOps Core already exposes — component health,
 * providers, client permissions, and the console's own resolved identity —
 * and must not pretend to powers (shell, restarts) the backend does not have.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { SystemPage } from '../SystemPage'
import {
  configApi,
  systemApi,
  type SystemStatus,
} from '@/services/lifeops'

vi.mock('@/services/lifeops', async () => {
  const actual = await vi.importActual<typeof import('@/services/lifeops')>(
    '@/services/lifeops',
  )
  return {
    ...actual,
    systemApi: {
      status: vi.fn(),
      health: vi.fn(),
    },
    configApi: {
      updateSystem: vi.fn(),
    },
  }
})

const CONSOLE_CLIENT = {
  client_id: 'lifeops-console',
  role: 'operator',
  display_name: 'LifeOps Console',
  description: 'The operator console you are looking at.',
  capabilities: ['tasks:write', 'config:write'],
}

function makeStatus(overrides: Partial<SystemStatus> = {}): SystemStatus {
  return {
    components: {
      lifeops_core: { healthy: true, detail: 'running' },
      nornicdb: { healthy: true, detail: 'bolt reachable' },
      secret_store: { healthy: false, detail: 'not configured' },
      safe_mode: false,
    },
    providers: [
      {
        id: 'deepseek',
        display_name: 'DeepSeek',
        category: 'llm',
        summary: 'Chat model',
        state: 'not_configured',
        enabled: false,
        available_in_phase: 1,
        settings: {},
        secrets: {},
        missing_required: ['api_key'],
        capabilities: ['llm.chat'],
        last_health: null,
      },
    ],
    system: {
      display_name: 'Gene',
      timezone: 'UTC',
      household_name: 'Home',
      primary_person_id: null,
      local_url: null,
      setup_completed: true,
      safe_mode: false,
    },
    clients: [
      CONSOLE_CLIENT,
      {
        client_id: 'hermes-personal',
        role: 'agent',
        display_name: 'Hermes',
        description: 'Personal Hermes instance.',
        capabilities: ['tasks:write', 'memory:write'],
      },
    ],
    requesting_client: CONSOLE_CLIENT,
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
        <SystemPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const mockedSystem = vi.mocked(systemApi)
const mockedConfig = vi.mocked(configApi)

beforeEach(() => {
  mockedSystem.status.mockResolvedValue(makeStatus())
  mockedSystem.health.mockResolvedValue({
    status: 'ok',
    components: { lifeops_core: { healthy: true, detail: 'running' } },
  })
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('LifeOps System', () => {
  it('reports component health with details', async () => {
    renderPage()
    expect(await screen.findByText('NornicDB')).toBeInTheDocument()
    expect(screen.getByText('bolt reachable')).toBeInTheDocument()
    expect(screen.getByText('Secret store')).toBeInTheDocument()
    // The unhealthy component is flagged, not hidden.
    expect(screen.getByText('Unreachable')).toBeInTheDocument()
  })

  it('shows the overall health signal from GET /health', async () => {
    renderPage()
    expect(await screen.findByText('LifeOps Core is healthy')).toBeInTheDocument()
    expect(mockedSystem.health).toHaveBeenCalled()
  })

  it('flags a degraded overall status', async () => {
    mockedSystem.health.mockResolvedValue({
      status: 'degraded',
      components: { nornicdb: { healthy: false, detail: 'unreachable' } },
    })
    renderPage()
    expect(
      await screen.findByText('LifeOps Core reports a problem'),
    ).toBeInTheDocument()
  })

  it('shows which identity the console is acting as', async () => {
    renderPage()
    expect(await screen.findByText('This console')).toBeInTheDocument()
    // The console's own resolved grant, distinct from the full client list.
    expect(screen.getAllByText('lifeops-console').length).toBeGreaterThanOrEqual(2)
    expect(screen.getAllByText('config:write').length).toBeGreaterThanOrEqual(2)
  })

  it('lists every connected client with its capabilities', async () => {
    renderPage()
    expect(await screen.findByText('Hermes')).toBeInTheDocument()
    expect(screen.getByText('memory:write')).toBeInTheDocument()
  })

  it('toggles safe mode through the system config endpoint', async () => {
    mockedConfig.updateSystem.mockResolvedValue(makeStatus().system)
    renderPage()
    await screen.findByText('Safe mode is off')

    await userEvent.click(screen.getByRole('button', { name: /turn on/i }))

    expect(mockedConfig.updateSystem).toHaveBeenCalledWith({ safe_mode: true })
  })

  it('shows the error surface when status cannot be loaded', async () => {
    mockedSystem.status.mockRejectedValue(new Error('Network Error'))
    renderPage()
    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument()
  })
})
