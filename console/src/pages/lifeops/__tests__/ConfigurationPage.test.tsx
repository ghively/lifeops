/**
 * Configuration screen behaviour.
 *
 * Two properties matter most here and are both security-relevant:
 * forms are built from the server's schema (so no provider needs bespoke UI),
 * and a secret value never travels back out to the browser.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ConfigurationPage } from '../ConfigurationPage'
import { configApi, type ProviderEntry } from '@/services/lifeops'

vi.mock('@/services/lifeops', async () => {
  const actual = await vi.importActual<typeof import('@/services/lifeops')>(
    '@/services/lifeops',
  )
  return {
    ...actual,
    configApi: {
      listProviders: vi.fn(),
      getProvider: vi.fn(),
      updateProvider: vi.fn(),
      testProvider: vi.fn(),
      discover: vi.fn(),
      getSystem: vi.fn(),
      updateSystem: vi.fn(),
    },
  }
})

const deepseek: ProviderEntry = {
  definition: {
    id: 'deepseek',
    category: 'llm',
    display_name: 'DeepSeek',
    summary: 'Primary language and reasoning engine used by Hermes.',
    available_in_phase: 0,
    docs_url: null,
    capabilities: ['chat'],
    fields: [
      {
        name: 'enabled',
        kind: 'boolean',
        label: 'Enabled',
        required: false,
        description: '',
        default: false,
        placeholder: null,
        options: [],
        options_from: null,
        minimum: null,
        maximum: null,
        step: null,
        advanced: false,
      },
      {
        name: 'api_key',
        kind: 'secret',
        label: 'API key',
        required: true,
        description: '',
        default: null,
        placeholder: 'sk-...',
        options: [],
        options_from: null,
        minimum: null,
        maximum: null,
        step: null,
        advanced: false,
      },
      {
        name: 'max_tokens',
        kind: 'number',
        label: 'Max tokens',
        required: false,
        description: '',
        default: 4096,
        placeholder: null,
        options: [],
        options_from: null,
        minimum: 1,
        maximum: null,
        step: null,
        advanced: true,
      },
    ],
  },
  status: {
    id: 'deepseek',
    display_name: 'DeepSeek',
    category: 'llm',
    summary: 'Primary language and reasoning engine used by Hermes.',
    state: 'not_configured',
    enabled: false,
    available_in_phase: 0,
    settings: { enabled: false, max_tokens: 4096 },
    secrets: { api_key: { configured: false, fingerprint: null } },
    missing_required: ['api_key', 'model'],
    capabilities: ['chat'],
    last_health: null,
  },
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <ConfigurationPage />
    </QueryClientProvider>,
  )
}

const mockedConfig = vi.mocked(configApi)

beforeEach(() => {
  mockedConfig.listProviders.mockResolvedValue([deepseek])
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('LifeOps Configuration', () => {
  it('renders a provider with its state and what it still needs', async () => {
    renderPage()
    expect(await screen.findByText('DeepSeek')).toBeInTheDocument()
    expect(screen.getByText('Not configured')).toBeInTheDocument()
    expect(screen.getByText(/Needs: api_key, model/)).toBeInTheDocument()
  })

  it('builds the form from the server-supplied schema', async () => {
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: 'Configure' }))

    expect(screen.getByLabelText('Enabled')).toBeInTheDocument()
    expect(screen.getByLabelText(/API key/)).toBeInTheDocument()
    // Advanced fields stay hidden until asked for.
    expect(screen.queryByLabelText(/Max tokens/)).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Show advanced' }))
    expect(screen.getByLabelText(/Max tokens/)).toBeInTheDocument()
  })

  it('renders a secret field as write-only', async () => {
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: 'Configure' }))

    const input = screen.getByLabelText(/API key/)
    expect(input).toHaveAttribute('type', 'password')
    expect(input).toHaveValue('')
  })

  it('never displays a stored secret, only that one exists', async () => {
    mockedConfig.listProviders.mockResolvedValue([
      {
        ...deepseek,
        status: {
          ...deepseek.status,
          secrets: { api_key: { configured: true, fingerprint: 'a1b2c3d4e5f6' } },
          missing_required: ['model'],
        },
      },
    ])
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: 'Configure' }))

    const input = screen.getByLabelText(/API key/)
    expect(input).toHaveValue('')
    expect(input).toHaveAttribute('placeholder', expect.stringContaining('a1b2c3d4e5f6'))
  })

  it('sends only the fields the user changed', async () => {
    mockedConfig.updateProvider.mockResolvedValue(deepseek.status)
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: 'Configure' }))

    await userEvent.type(screen.getByLabelText(/API key/), 'sk-abc123')
    await userEvent.click(screen.getByRole('button', { name: /save/i }))

    await waitFor(() =>
      expect(mockedConfig.updateProvider).toHaveBeenCalledWith('deepseek', {
        api_key: 'sk-abc123',
      }),
    )
  })

  it('reports a rejected value from the server', async () => {
    const { LifeOpsError } = await vi.importActual<
      typeof import('@/services/lifeops')
    >('@/services/lifeops')
    mockedConfig.updateProvider.mockRejectedValue(
      new LifeOpsError('validation_error', 'max_tokens must be at least 1', 422),
    )
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: 'Configure' }))
    await userEvent.type(screen.getByLabelText(/API key/), 'x')
    await userEvent.click(screen.getByRole('button', { name: /save/i }))

    expect(
      await screen.findByText('max_tokens must be at least 1'),
    ).toBeInTheDocument()
  })

  it('states plainly that secrets stay out of the database', async () => {
    renderPage()
    expect(
      await screen.findByText(/never written to NornicDB/i),
    ).toBeInTheDocument()
  })
})
