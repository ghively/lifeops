/**
 * Hermes screen behaviour (BUILD_SPEC section 20).
 *
 * The screen shows what LifeOps Core actually knows about Hermes — model,
 * provider health, routines, recent audited actions — and is honest about
 * the items the spec asks for that have no real backend today (a live MCP
 * connection registry, a separate memory provider, instantiated skills),
 * rather than fabricating a state for them.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { HermesPage } from '../HermesPage'
import {
  auditApi,
  systemApi,
  voiceApi,
  workflowTemplatesApi,
  type AuditRecord,
  type ProviderStatus,
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
      getActivity: vi.fn(),
    },
    voiceApi: {
      getModeStatus: vi.fn(),
    },
    auditApi: {
      read: vi.fn(),
    },
    workflowTemplatesApi: {
      list: vi.fn(),
    },
  }
})

function makeProvider(overrides: Partial<ProviderStatus> = {}): ProviderStatus {
  return {
    id: 'deepseek',
    display_name: 'DeepSeek',
    category: 'llm',
    summary: 'Chat model',
    state: 'healthy',
    enabled: true,
    available_in_phase: 1,
    settings: { model: 'deepseek-chat' },
    secrets: {},
    missing_required: [],
    capabilities: ['llm.chat'],
    last_health: null,
    ...overrides,
  }
}

const CONSOLE_CLIENT = {
  client_id: 'lifeops-console',
  role: 'operator',
  display_name: 'LifeOps Console',
  description: 'The operator console you are looking at.',
  capabilities: ['tasks:write'],
}

function makeStatus(overrides: Partial<SystemStatus> = {}): SystemStatus {
  return {
    components: {
      lifeops_core: { healthy: true, detail: 'running' },
      nornicdb: { healthy: true, detail: 'bolt reachable' },
      secret_store: { healthy: false, detail: 'not configured' },
      safe_mode: false,
    },
    providers: [makeProvider()],
    system: {
      display_name: 'Gene',
      timezone: 'UTC',
      household_name: 'Home',
      primary_person_id: null,
      local_url: null,
      setup_completed: true,
      safe_mode: false,
      voice_mode: 'quick_cloud',
    },
    clients: [CONSOLE_CLIENT],
    requesting_client: CONSOLE_CLIENT,
    ...overrides,
  }
}

function makeAuditRecord(overrides: Partial<AuditRecord> = {}): AuditRecord {
  return {
    id: 'audit_01',
    requester: null,
    user: null,
    client: 'hermes-personal',
    session: null,
    intent: 'create_appointment_hold',
    tool: 'calendar',
    risk: 'R3',
    approval: null,
    action: 'action_01',
    target: null,
    result: 'held',
    verification: null,
    timestamp: '2026-08-18T10:30:00Z',
    trace_id: null,
    details: {},
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
        <HermesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const mockedSystem = vi.mocked(systemApi)
const mockedVoice = vi.mocked(voiceApi)
const mockedAudit = vi.mocked(auditApi)
const mockedRoutines = vi.mocked(workflowTemplatesApi)

beforeEach(() => {
  mockedSystem.status.mockResolvedValue(makeStatus())
  mockedSystem.getActivity.mockResolvedValue([])
  mockedVoice.getModeStatus.mockResolvedValue({
    mode: 'quick_cloud',
    tts_active: 'elevenlabs',
    tts_fallback: null,
    asr_active: null,
    asr_fallback: null,
  })
  mockedAudit.read.mockResolvedValue({ records: [], total: 0 })
  mockedRoutines.list.mockResolvedValue({ templates: [], total: 0 })
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('Hermes', () => {
  it('shows the primary model provider and current model', async () => {
    renderPage()
    expect(await screen.findByText('DeepSeek')).toBeInTheDocument()
    expect(screen.getByText('deepseek-chat')).toBeInTheDocument()
  })

  it('shows an honest "no model selected" state when unconfigured', async () => {
    mockedSystem.status.mockResolvedValue(
      makeStatus({
        providers: [makeProvider({ state: 'not_configured', settings: {} })],
      }),
    )
    renderPage()
    expect(await screen.findByText('No model selected')).toBeInTheDocument()
  })

  it('labels MCP connection and memory provider as not tracked, honestly', async () => {
    renderPage()
    expect(await screen.findByText('LifeOps MCP')).toBeInTheDocument()
    expect(screen.getByText('Memory provider')).toBeInTheDocument()
    expect(screen.getAllByText('Not tracked').length).toBeGreaterThanOrEqual(2)
    expect(
      screen.getByText(/does not keep a connection registry for mcp clients/i),
    ).toBeInTheDocument()
  })

  it('shows Telegram provider status', async () => {
    mockedSystem.status.mockResolvedValue(
      makeStatus({
        providers: [
          makeProvider(),
          makeProvider({
            id: 'telegram',
            display_name: 'Telegram',
            category: 'messaging',
            state: 'configured',
          }),
        ],
      }),
    )
    renderPage()
    expect(await screen.findByText('Telegram')).toBeInTheDocument()
  })

  it('summarizes routines and links to the Routines screen', async () => {
    mockedRoutines.list.mockResolvedValue({
      templates: [
        {
          id: 'wf_01',
          name: 'Weekly review',
          description: null,
          steps: [],
          trigger: 'schedule',
          next_run_at: null,
          enabled: true,
          created_at: '2026-08-01T00:00:00Z',
          updated_at: '2026-08-01T00:00:00Z',
          created_by_client: 'hermes-personal',
        },
        {
          id: 'wf_02',
          name: 'Paused routine',
          description: null,
          steps: [],
          trigger: 'manual',
          next_run_at: null,
          enabled: false,
          created_at: '2026-08-01T00:00:00Z',
          updated_at: '2026-08-01T00:00:00Z',
          created_by_client: 'hermes-personal',
        },
      ],
      total: 2,
    })
    renderPage()
    expect(await screen.findByText('1 of 2 routines enabled')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /manage on routines/i })).toHaveAttribute(
      'href',
      '/routines',
    )
  })

  it('has an honest empty state for routines', async () => {
    renderPage()
    expect(await screen.findByText('No routines yet.')).toBeInTheDocument()
  })

  it('points at the shipped skills instead of claiming none exist', async () => {
    renderPage()
    expect(await screen.findByText(/nine lifeops skills ship/i)).toBeInTheDocument()
  })

  it('shows recent actions attributed to Hermes from the audit log', async () => {
    mockedAudit.read.mockResolvedValue({
      records: [
        makeAuditRecord({ id: 'audit_01', client: 'hermes-personal' }),
        makeAuditRecord({ id: 'audit_02', client: 'lifeops-console', intent: 'record_bill' }),
      ],
      total: 2,
    })
    renderPage()
    expect(
      await screen.findByText('Hermes held a calendar appointment.'),
    ).toBeInTheDocument()
    // Only Hermes-attributed records show here — the console's own action does not.
    expect(screen.queryByText('record_bill')).not.toBeInTheDocument()
  })

  it('has an honest empty state for recent actions', async () => {
    renderPage()
    expect(
      await screen.findByText('No recent actions recorded from Hermes.'),
    ).toBeInTheDocument()
  })

  it('shows last recorded activity time, not a fabricated presence indicator', async () => {
    mockedAudit.read.mockResolvedValue({
      records: [makeAuditRecord({ client: 'hermes-personal', timestamp: '2026-08-18T10:30:00Z' })],
      total: 1,
    })
    renderPage()
    expect(await screen.findByText(/last recorded activity/i)).toBeInTheDocument()
    expect(
      screen.getByText(/not a real-time presence check/i),
    ).toBeInTheDocument()
  })

  it('shows an honest "no activity recorded" state when Hermes has never been seen', async () => {
    renderPage()
    expect(
      await screen.findByText(/no activity recorded from hermes yet/i),
    ).toBeInTheDocument()
  })

  it('shows the error surface when status cannot be loaded', async () => {
    mockedSystem.status.mockRejectedValue(new Error('Network Error'))
    renderPage()
    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument()
  })
})
