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
import { LifeOpsError, authApi, configApi, voiceApi, type ProviderEntry } from '@/services/lifeops'

vi.mock('@/services/lifeops', async () => {
  const actual = await vi.importActual<typeof import('@/services/lifeops')>(
    '@/services/lifeops',
  )
  return {
    ...actual,
    authApi: {
      me: vi.fn(),
      login: vi.fn(),
      setPassword: vi.fn(),
    },
    configApi: {
      listProviders: vi.fn(),
      getProvider: vi.fn(),
      updateProvider: vi.fn(),
      testProvider: vi.fn(),
      discover: vi.fn(),
      getSystem: vi.fn(),
      updateSystem: vi.fn(),
    },
    voiceApi: {
      previewVoice: vi.fn(),
      getModeStatus: vi.fn(),
      loadProvider: vi.fn(),
      unloadProvider: vi.fn(),
    },
  }
})

// jsdom does not implement the Blob object URL APIs the preview player uses.
if (!URL.createObjectURL) {
  URL.createObjectURL = vi.fn(() => 'blob:mock-url')
}
if (!URL.revokeObjectURL) {
  URL.revokeObjectURL = vi.fn()
}

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

const elevenlabs: ProviderEntry = {
  definition: {
    id: 'elevenlabs',
    category: 'voice_tts',
    display_name: 'ElevenLabs',
    summary: 'Fastest path to high-quality streamed speech.',
    available_in_phase: 5,
    docs_url: null,
    capabilities: ['tts', 'streaming_tts', 'list_voices', 'list_models', 'health_check'],
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
        name: 'voice_id',
        kind: 'select',
        label: 'Voice',
        required: true,
        description: '',
        default: null,
        placeholder: null,
        options: [],
        options_from: 'voices',
        minimum: null,
        maximum: null,
        step: null,
        advanced: false,
      },
    ],
  },
  status: {
    id: 'elevenlabs',
    display_name: 'ElevenLabs',
    category: 'voice_tts',
    summary: 'Fastest path to high-quality streamed speech.',
    state: 'not_configured',
    enabled: false,
    available_in_phase: 5,
    settings: { enabled: false, voice_id: null },
    secrets: { api_key: { configured: false, fingerprint: null } },
    missing_required: ['api_key', 'voice_id'],
    capabilities: ['tts', 'streaming_tts', 'list_voices', 'list_models', 'health_check'],
    last_health: null,
  },
}

const localTts: ProviderEntry = {
  definition: {
    id: 'local_tts',
    category: 'voice_tts',
    display_name: 'Local TTS (RTX)',
    summary: 'GPU-accelerated local speech synthesis.',
    available_in_phase: 6,
    docs_url: null,
    capabilities: ['tts', 'streaming_tts', 'health_check'],
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
    ],
  },
  status: {
    id: 'local_tts',
    display_name: 'Local TTS (RTX)',
    category: 'voice_tts',
    summary: 'GPU-accelerated local speech synthesis.',
    state: 'not_configured',
    enabled: false,
    available_in_phase: 6,
    settings: { enabled: false, model: null, device: 'cuda:0' },
    secrets: {},
    missing_required: ['model'],
    capabilities: ['tts', 'streaming_tts', 'health_check'],
    last_health: null,
  },
}

const mockedConfig = vi.mocked(configApi)
const mockedAuth = vi.mocked(authApi)
const mockedVoice = vi.mocked(voiceApi)

beforeEach(() => {
  mockedConfig.listProviders.mockResolvedValue([deepseek])
  mockedConfig.getSystem.mockResolvedValue({
    display_name: 'LifeOps',
    timezone: 'UTC',
    household_name: '',
    primary_person_id: null,
    local_url: null,
    setup_completed: false,
    safe_mode: false,
    voice_mode: 'quick_cloud',
  })
  mockedVoice.getModeStatus.mockResolvedValue({
    mode: 'quick_cloud',
    tts_active: null,
    tts_fallback: null,
    asr_active: null,
    asr_fallback: null,
  })
  mockedAuth.me.mockResolvedValue({
    client_id: 'lifeops-console',
    display_name: 'LifeOps Console',
    auth_enabled: false,
  })
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

describe('Voice mode', () => {
  it('shows the three BUILD_SPEC section 29 pairings', async () => {
    renderPage()
    expect(await screen.findByText('Quick Cloud')).toBeInTheDocument()
    expect(screen.getByText('Hybrid Recommended')).toBeInTheDocument()
    expect(screen.getByText('Local')).toBeInTheDocument()
  })

  it('saves the selected mode as a system setting', async () => {
    mockedConfig.updateSystem.mockResolvedValue({
      display_name: 'LifeOps',
      timezone: 'UTC',
      household_name: '',
      primary_person_id: null,
      local_url: null,
      setup_completed: false,
      safe_mode: false,
      voice_mode: 'hybrid',
    })
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: /Hybrid Recommended/ }))

    await waitFor(() =>
      expect(mockedConfig.updateSystem).toHaveBeenCalledWith({ voice_mode: 'hybrid' }),
    )
  })

  it('shows the active and fallback provider per BUILD_SPEC section 95', async () => {
    mockedVoice.getModeStatus.mockResolvedValue({
      mode: 'local',
      tts_active: 'local_tts',
      tts_fallback: 'elevenlabs',
      asr_active: 'local_asr',
      asr_fallback: null,
    })
    renderPage()

    expect(await screen.findByText(/active local_tts/)).toBeInTheDocument()
    expect(screen.getByText(/fallback elevenlabs/)).toBeInTheDocument()
    expect(screen.getByText(/active local_asr/)).toBeInTheDocument()
  })
})

describe('Local voice (BUILD_SPEC section 95)', () => {
  it('offers load/unload controls only for the local voice providers', async () => {
    mockedConfig.listProviders.mockResolvedValue([deepseek, localTts])
    renderPage()

    const configureButtons = await screen.findAllByRole('button', { name: 'Configure' })
    await userEvent.click(configureButtons[0])
    expect(screen.queryByRole('button', { name: 'Load model' })).not.toBeInTheDocument()

    await userEvent.click(configureButtons[1])
    expect(screen.getByRole('button', { name: 'Load model' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Unload model' })).toBeInTheDocument()
  })

  it('reports the server message rather than pretending a model loaded', async () => {
    mockedConfig.listProviders.mockResolvedValue([localTts])
    mockedVoice.loadProvider.mockResolvedValue({
      provider: 'local_tts',
      loaded: false,
      message: 'no local TTS runtime is wired up yet',
    })
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Configure' }))
    await userEvent.click(screen.getByRole('button', { name: 'Load model' }))

    expect(mockedVoice.loadProvider).toHaveBeenCalledWith('local_tts')
    expect(
      await screen.findByText('no local TTS runtime is wired up yet'),
    ).toBeInTheDocument()
  })
})

describe('ElevenLabs preview', () => {
  it('offers a preview button only for ElevenLabs', async () => {
    mockedConfig.listProviders.mockResolvedValue([deepseek, elevenlabs])
    renderPage()

    const configureButtons = await screen.findAllByRole('button', { name: 'Configure' })
    await userEvent.click(configureButtons[0])
    expect(screen.queryByText('Preview text')).not.toBeInTheDocument()

    await userEvent.click(configureButtons[1])
    expect(await screen.findByText('Preview text')).toBeInTheDocument()
  })

  it('plays back synthesized audio without saving anything', async () => {
    mockedConfig.listProviders.mockResolvedValue([elevenlabs])
    mockedVoice.previewVoice.mockResolvedValue(new Blob(['audio'], { type: 'audio/mpeg' }))
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Configure' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Preview voice' }))

    await waitFor(() => expect(mockedVoice.previewVoice).toHaveBeenCalled())
    expect(mockedConfig.updateProvider).not.toHaveBeenCalled()
  })

  it('shows the server message when preview fails', async () => {
    mockedConfig.listProviders.mockResolvedValue([elevenlabs])
    mockedVoice.previewVoice.mockRejectedValue(
      new LifeOpsError(
        'provider_not_configured',
        'no text-to-speech provider is enabled and fully configured yet',
        400,
      ),
    )
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Configure' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Preview voice' }))

    expect(
      await screen.findByText(/no text-to-speech provider is enabled/),
    ).toBeInTheDocument()
  })
})

describe('Console access', () => {
  it('offers first setup without a current password when auth is off', async () => {
    renderPage()
    expect(
      await screen.findByText(/Authentication is off/i),
    ).toBeInTheDocument()
    expect(screen.queryByLabelText('Current password')).not.toBeInTheDocument()

    mockedAuth.setPassword.mockResolvedValue({ auth_enabled: true })
    await userEvent.type(screen.getByLabelText('Console password'), 'correct horse')
    await userEvent.click(screen.getByRole('button', { name: 'Set password' }))

    await waitFor(() =>
      expect(mockedAuth.setPassword).toHaveBeenCalledWith('correct horse', undefined),
    )
  })

  it('requires the current password once auth is on', async () => {
    mockedAuth.me.mockResolvedValue({
      client_id: 'lifeops-console',
      display_name: 'LifeOps Console',
      auth_enabled: true,
    })
    renderPage()
    expect(await screen.findByText(/Authentication is on/i)).toBeInTheDocument()

    mockedAuth.setPassword.mockResolvedValue({ auth_enabled: true })
    await userEvent.type(screen.getByLabelText('Current password'), 'old password')
    await userEvent.type(screen.getByLabelText('New password'), 'new password')
    await userEvent.click(screen.getByRole('button', { name: 'Change password' }))

    await waitFor(() =>
      expect(mockedAuth.setPassword).toHaveBeenCalledWith('new password', 'old password'),
    )
  })

  it('shows the server reason when a change is refused', async () => {
    const { LifeOpsError } = await vi.importActual<
      typeof import('@/services/lifeops')
    >('@/services/lifeops')
    mockedAuth.setPassword.mockRejectedValue(
      new LifeOpsError(
        'invalid_credentials',
        'the current console password did not match',
        401,
      ),
    )
    renderPage()
    await userEvent.type(await screen.findByLabelText('Console password'), 'correct horse')
    await userEvent.click(screen.getByRole('button', { name: 'Set password' }))

    expect(
      await screen.findByText('the current console password did not match'),
    ).toBeInTheDocument()
  })
})
