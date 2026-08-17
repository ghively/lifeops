/**
 * Configuration (BUILD_SPEC sections 22, 25, 26).
 *
 * Every form on this page is rendered from the provider's field schema, served
 * by LifeOps Core. Adding a provider needs no change here — which is the whole
 * point: the user configures real credentials after deployment, and no
 * developer is ever blocked waiting for them.
 *
 * Secret fields are write-only. The server returns `configured` and a
 * fingerprint, never the value, so a secret cannot leak back out through the
 * UI that set it.
 */

import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Loader2, Settings2, ShieldCheck, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { QueryError } from '@/components/QueryError'
import { cn } from '@/lib/utils'
import {
  LifeOpsError,
  PROVIDER_STATE_LABELS,
  authApi,
  configApi,
  errorMessage,
  voiceApi,
  type ProviderEntry,
  type ProviderField,
  type ProviderState,
  type VoiceMode,
} from '@/services/lifeops'

/** BUILD_SPEC section 95 — the two local voice adapters phase 6 adds. */
const LOCAL_VOICE_PROVIDER_IDS = new Set(['local_tts', 'local_asr'])

const STATE_TONE: Record<ProviderState, string> = {
  healthy: 'bg-green-100 text-green-800',
  configured: 'bg-blue-100 text-blue-800',
  unhealthy: 'bg-red-100 text-red-800',
  not_configured: 'bg-amber-100 text-amber-800',
  disabled: 'bg-muted text-muted-foreground',
}

const CATEGORY_LABELS: Record<string, string> = {
  llm: 'AI',
  voice_tts: 'Voice',
  voice_asr: 'Voice',
  messaging: 'Messaging',
  calendar: 'Productivity',
  email: 'Productivity',
  browser: 'Automation',
  telephony: 'Automation',
}

const CATEGORY_ORDER = [
  'AI',
  'Voice',
  'Messaging',
  'Productivity',
  'Automation',
  'Other',
]

/** BUILD_SPEC section 29 — the three ASR/TTS pairings the Console offers. */
const VOICE_MODES: Array<{ value: VoiceMode; label: string; description: string }> = [
  { value: 'quick_cloud', label: 'Quick Cloud', description: 'ASR: configurable · TTS: ElevenLabs' },
  {
    value: 'hybrid',
    label: 'Hybrid Recommended',
    description: 'ASR: local (RTX) · TTS: ElevenLabs',
  },
  { value: 'local', label: 'Local', description: 'ASR: local (RTX) · TTS: local (RTX)' },
]

function FieldInput({
  field,
  entry,
  value,
  onChange,
}: {
  field: ProviderField
  entry: ProviderEntry
  value: unknown
  onChange: (value: unknown) => void
}) {
  const id = `${entry.definition.id}-${field.name}`

  if (field.kind === 'boolean') {
    return (
      <label className="flex items-center gap-2 text-sm" htmlFor={id}>
        <input
          id={id}
          type="checkbox"
          className="h-4 w-4"
          checked={Boolean(value)}
          onChange={(event) => onChange(event.target.checked)}
        />
        {field.label}
      </label>
    )
  }

  if (field.kind === 'secret') {
    const stored = entry.status.secrets[field.name]
    return (
      <div className="space-y-1">
        <label className="text-sm font-medium" htmlFor={id}>
          {field.label}
          {field.required && <span className="ml-1 text-red-500">*</span>}
        </label>
        <Input
          id={id}
          type="password"
          autoComplete="off"
          value={(value as string) ?? ''}
          placeholder={
            stored?.configured
              ? `configured · ${stored.fingerprint ?? 'stored'}`
              : (field.placeholder ?? 'not configured')
          }
          onChange={(event) => onChange(event.target.value)}
        />
        <p className="text-xs text-muted-foreground">
          {stored?.configured
            ? 'Stored encrypted outside the database. Leave blank to keep it; clear and save to remove it.'
            : 'Stored encrypted outside the database and never returned by the API.'}
        </p>
      </div>
    )
  }

  if (field.kind === 'select' && field.options.length > 0) {
    return (
      <div className="space-y-1">
        <label className="text-sm font-medium" htmlFor={id}>
          {field.label}
          {field.required && <span className="ml-1 text-red-500">*</span>}
        </label>
        <select
          id={id}
          className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
          value={(value as string) ?? ''}
          onChange={(event) => onChange(event.target.value)}
        >
          <option value="">Not set</option>
          {field.options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>
    )
  }

  return (
    <div className="space-y-1">
      <label className="text-sm font-medium" htmlFor={id}>
        {field.label}
        {field.required && <span className="ml-1 text-red-500">*</span>}
      </label>
      <Input
        id={id}
        type={field.kind === 'number' ? 'number' : 'text'}
        value={(value as string | number | undefined) ?? ''}
        placeholder={field.placeholder ?? undefined}
        min={field.minimum ?? undefined}
        max={field.maximum ?? undefined}
        step={field.step ?? undefined}
        onChange={(event) =>
          onChange(
            field.kind === 'number'
              ? event.target.value === ''
                ? null
                : Number(event.target.value)
              : event.target.value,
          )
        }
      />
      {field.description && (
        <p className="text-xs text-muted-foreground">{field.description}</p>
      )}
      {field.options_from && field.options.length === 0 && (
        <p className="text-xs text-muted-foreground">
          Choices are discovered from the provider once it is connected.
        </p>
      )}
    </div>
  )
}

/**
 * ElevenLabs' Preview voice button (BUILD_SPEC section 27): synthesize a
 * sample line and play it back in the browser. Never saves anything and
 * needs no Hermes, so a voice can be auditioned before it is set as default.
 *
 * The only per-provider custom UX on this page — justified because listening
 * to a voice before committing to it is not something a generic field
 * schema can express (AGENTS.md: no bespoke settings page unless it
 * materially helps).
 */
function VoicePreview({
  voiceId,
  modelId,
}: {
  voiceId: string | undefined
  modelId: string | undefined
}) {
  const [text, setText] = useState('This is a preview of the selected voice.')
  const [audioUrl, setAudioUrl] = useState<string | null>(null)

  const preview = useMutation({
    mutationFn: () => voiceApi.previewVoice({ text, voice_id: voiceId, model_id: modelId }),
    onSuccess: (blob) => {
      setAudioUrl((previous) => {
        if (previous) URL.revokeObjectURL(previous)
        return URL.createObjectURL(blob)
      })
    },
  })

  return (
    <div className="space-y-2 rounded-md border border-border/60 bg-muted/20 p-3">
      <label className="text-sm font-medium" htmlFor="voice-preview-text">
        Preview text
      </label>
      <Input
        id="voice-preview-text"
        value={text}
        maxLength={2000}
        onChange={(event) => setText(event.target.value)}
      />
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => preview.mutate()}
          disabled={preview.isPending || text.trim().length === 0}
        >
          {preview.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            'Preview voice'
          )}
        </Button>
        {audioUrl && <audio controls src={audioUrl} className="h-8" />}
      </div>
      {preview.isError && (
        <p className="text-xs text-red-600">{errorMessage(preview.error)}</p>
      )}
    </div>
  )
}

/**
 * Load/unload controls for the two local voice adapters (BUILD_SPEC section
 * 95). No ML runtime ships with this codebase (section 105), so both
 * buttons report — honestly, never a fake success — why nothing loaded in
 * this environment; the point is that the control exists and tells the
 * truth once a real runtime is installed and selected.
 */
function LocalVoiceControls({ providerId }: { providerId: string }) {
  const [message, setMessage] = useState<string | null>(null)

  const load = useMutation({
    mutationFn: () => voiceApi.loadProvider(providerId),
    onSuccess: (result) => setMessage(result.message),
  })
  const unload = useMutation({
    mutationFn: () => voiceApi.unloadProvider(providerId),
    onSuccess: (result) => setMessage(result.message),
  })

  return (
    <div className="space-y-2 rounded-md border border-border/60 bg-muted/20 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => load.mutate()}
          disabled={load.isPending}
        >
          {load.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Load model'}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => unload.mutate()}
          disabled={unload.isPending}
        >
          {unload.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Unload model'}
        </Button>
      </div>
      {message && <p className="text-xs text-muted-foreground">{message}</p>}
      {(load.isError || unload.isError) && (
        <p className="text-xs text-red-600">
          {errorMessage((load.error ?? unload.error) as unknown)}
        </p>
      )}
    </div>
  )
}

function ProviderCard({ entry }: { entry: ProviderEntry }) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [draft, setDraft] = useState<Record<string, unknown>>({})
  const [error, setError] = useState<string | null>(null)

  const { definition, status } = entry

  const save = useMutation({
    mutationFn: (values: Record<string, unknown>) =>
      configApi.updateProvider(definition.id, values),
    onSuccess: () => {
      setDraft({})
      setError(null)
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'providers'] })
    },
    onError: (err) => {
      setError(err instanceof LifeOpsError ? err.message : 'Could not save.')
    },
  })

  const test = useMutation({
    mutationFn: () => configApi.testProvider(definition.id),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'providers'] }),
  })

  const valueFor = (field: ProviderField): unknown =>
    field.name in draft
      ? draft[field.name]
      : field.kind === 'secret'
        ? ''
        : status.settings[field.name]

  const visibleFields = definition.fields.filter(
    (field) => showAdvanced || !field.advanced,
  )

  return (
    <div className="rounded-lg border border-border/60 bg-card">
      <div className="flex items-start justify-between gap-4 px-4 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="font-medium">{definition.display_name}</h3>
            <span
              className={cn(
                'rounded-full px-2 py-0.5 text-xs font-medium',
                STATE_TONE[status.state],
              )}
            >
              {PROVIDER_STATE_LABELS[status.state]}
            </span>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{definition.summary}</p>
          {status.missing_required.length > 0 && (
            <p className="mt-1 text-xs text-amber-700">
              Needs: {status.missing_required.join(', ')}
            </p>
          )}
          {status.last_health && (
            <p className="mt-1 text-xs text-muted-foreground">
              Last check: {status.last_health.message || (status.last_health.healthy ? 'ok' : 'failed')}
              {typeof status.last_health.details.latency_ms === 'number' &&
                ` · ${status.last_health.details.latency_ms}ms`}
            </p>
          )}
        </div>
        <div className="flex shrink-0 gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => test.mutate()}
            disabled={test.isPending}
          >
            {test.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Test'}
          </Button>
          <Button variant="outline" size="sm" onClick={() => setOpen((v) => !v)}>
            {open ? 'Close' : 'Configure'}
          </Button>
        </div>
      </div>

      {open && (
        <form
          className="space-y-4 border-t border-border/60 px-4 py-4"
          onSubmit={(event) => {
            event.preventDefault()
            // Only changed fields are sent. A partial update means editing a
            // timeout never requires re-entering an API key.
            save.mutate(draft)
          }}
        >
          {visibleFields.map((field) => (
            <FieldInput
              key={field.name}
              field={field}
              entry={entry}
              value={valueFor(field)}
              onChange={(value) =>
                setDraft((prev) => ({ ...prev, [field.name]: value }))
              }
            />
          ))}

          {definition.id === 'elevenlabs' && (
            <VoicePreview
              voiceId={(draft.voice_id as string) || (status.settings.voice_id as string)}
              modelId={(draft.model_id as string) || (status.settings.model_id as string)}
            />
          )}

          {LOCAL_VOICE_PROVIDER_IDS.has(definition.id) && (
            <LocalVoiceControls providerId={definition.id} />
          )}

          {definition.fields.some((f) => f.advanced) && (
            <button
              type="button"
              className="text-xs text-muted-foreground underline"
              onClick={() => setShowAdvanced((v) => !v)}
            >
              {showAdvanced ? 'Hide advanced' : 'Show advanced'}
            </button>
          )}

          {error && (
            <p className="rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700">
              {error}
            </p>
          )}

          <div className="flex items-center gap-2">
            <Button
              type="submit"
              size="sm"
              disabled={Object.keys(draft).length === 0 || save.isPending}
            >
              {save.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Check className="h-3.5 w-3.5" />
              )}
              <span className="ml-1">Save</span>
            </Button>
            {Object.keys(draft).length > 0 && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => {
                  setDraft({})
                  setError(null)
                }}
              >
                <X className="h-3.5 w-3.5" />
                <span className="ml-1">Discard</span>
              </Button>
            )}
            {definition.available_in_phase > 0 && (
              <span className="ml-auto text-xs text-muted-foreground">
                Adapter arrives in phase {definition.available_in_phase}
              </span>
            )}
          </div>
        </form>
      )}
    </div>
  )
}

/**
 * Console access — the password that turns API authentication on
 * (SECURITY.md). Without one, the loopback API answers anyone on this
 * machine; setting one is the whole point of this card.
 */
function ConsoleAccessCard() {
  const queryClient = useQueryClient()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [saved, setSaved] = useState(false)

  const meQuery = useQuery({ queryKey: ['lifeops', 'auth', 'me'], queryFn: authApi.me })
  const authEnabled = meQuery.data?.auth_enabled ?? false

  const save = useMutation({
    mutationFn: () =>
      authApi.setPassword(newPassword, authEnabled ? currentPassword : undefined),
    onSuccess: () => {
      setSaved(true)
      setCurrentPassword('')
      setNewPassword('')
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'auth'] })
    },
  })

  return (
    <section className="space-y-3">
      <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
        Console access
      </h2>
      <div className="space-y-3 rounded-lg border border-border/60 bg-card px-4 py-3">
        <p className="text-sm text-muted-foreground">
          {authEnabled
            ? 'Authentication is on. Every API route requires the console password.'
            : 'Authentication is off — any process on this machine can use the API. Set a password to require it.'}
        </p>
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault()
            setSaved(false)
            save.mutate()
          }}
        >
          {authEnabled && (
            <div className="space-y-1">
              <label className="text-sm font-medium" htmlFor="console-current-password">
                Current password
              </label>
              <Input
                id="console-current-password"
                type="password"
                autoComplete="current-password"
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
              />
            </div>
          )}
          <div className="space-y-1">
            <label className="text-sm font-medium" htmlFor="console-new-password">
              {authEnabled ? 'New password' : 'Console password'}
            </label>
            <Input
              id="console-new-password"
              type="password"
              autoComplete="new-password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              At least 8 characters. Stored encrypted outside the database and never
              returned by the API.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Button
              type="submit"
              size="sm"
              disabled={save.isPending || newPassword.length < 8}
            >
              {save.isPending ? 'Saving…' : authEnabled ? 'Change password' : 'Set password'}
            </Button>
            {saved && !save.isPending && (
              <span className="inline-flex items-center gap-1 text-sm text-green-700">
                <Check className="h-4 w-4" />
                {authEnabled ? 'Password updated.' : 'Authentication is now on.'}
              </span>
            )}
          </div>
          {save.isError && (
            <p className="text-sm text-red-600">{errorMessage(save.error)}</p>
          )}
        </form>
      </div>
    </section>
  )
}

/**
 * BUILD_SPEC section 29's voice mode picker. Selects which ASR/TTS pairing
 * the Voice Bridge uses; switching modes is a LifeOps setting and never
 * touches the Hermes profile.
 */
function VoiceModeCard() {
  const queryClient = useQueryClient()
  const systemQuery = useQuery({ queryKey: ['lifeops', 'system'], queryFn: configApi.getSystem })
  // A pure readback (BUILD_SPEC section 95) — no live health check, so this
  // never fans out network calls just because Configuration was opened.
  const statusQuery = useQuery({
    queryKey: ['lifeops', 'voice', 'mode-status'],
    queryFn: voiceApi.getModeStatus,
  })

  const save = useMutation({
    mutationFn: (voice_mode: VoiceMode) => configApi.updateSystem({ voice_mode }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'system'] })
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'voice', 'mode-status'] })
    },
  })

  const current = save.variables ?? systemQuery.data?.voice_mode ?? 'quick_cloud'
  const status = statusQuery.data

  return (
    <section className="space-y-3">
      <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
        Voice mode
      </h2>
      <div className="grid gap-2 rounded-lg border border-border/60 bg-card p-3 sm:grid-cols-3">
        {VOICE_MODES.map((mode) => (
          <button
            key={mode.value}
            type="button"
            disabled={save.isPending}
            onClick={() => save.mutate(mode.value)}
            className={cn(
              'rounded-md border px-3 py-2 text-left text-sm transition-colors',
              current === mode.value
                ? 'border-primary bg-primary/10'
                : 'border-border/60 hover:bg-muted/40',
            )}
          >
            <div className="font-medium">{mode.label}</div>
            <div className="text-xs text-muted-foreground">{mode.description}</div>
          </button>
        ))}
      </div>
      {status && (
        <div className="grid gap-2 text-xs text-muted-foreground sm:grid-cols-2">
          <p>
            <span className="font-medium text-foreground">Speech-to-text:</span>{' '}
            active {status.asr_active ?? 'none configured'}
            {status.asr_fallback && ` · fallback ${status.asr_fallback}`}
          </p>
          <p>
            <span className="font-medium text-foreground">Text-to-speech:</span>{' '}
            active {status.tts_active ?? 'none configured'}
            {status.tts_fallback && ` · fallback ${status.tts_fallback}`}
          </p>
        </div>
      )}
      <p className="text-xs text-muted-foreground">
        Changes which provider Hermes&apos; Voice Bridge reaches for; it does not
        require reconfiguring Hermes itself.
      </p>
    </section>
  )
}

export function ConfigurationPage() {
  const providersQuery = useQuery({
    queryKey: ['lifeops', 'providers'],
    queryFn: configApi.listProviders,
  })

  const grouped = useMemo(() => {
    const groups = new Map<string, ProviderEntry[]>()
    for (const entry of providersQuery.data ?? []) {
      const label = CATEGORY_LABELS[entry.definition.category] ?? 'Other'
      groups.set(label, [...(groups.get(label) ?? []), entry])
    }
    return CATEGORY_ORDER.filter((label) => groups.has(label)).map((label) => ({
      label,
      entries: groups.get(label)!,
    }))
  }, [providersQuery.data])

  if (providersQuery.isError) {
    return (
      <div className="p-8">
        <QueryError
          message={errorMessage(providersQuery.error)}
          onRetry={() => void providersQuery.refetch()}
        />
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-3xl space-y-8 p-8">
      <header>
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <Settings2 className="h-5 w-5" />
          Configuration
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Connect providers here. Nothing is required to run LifeOps — every
          provider starts disabled.
        </p>
      </header>

      <div className="flex items-start gap-2 rounded-lg border border-border/60 bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
        <p>
          Secrets are encrypted with a key held outside the repository and are
          never written to NornicDB or returned by the API.
        </p>
      </div>

      <ConsoleAccessCard />

      <VoiceModeCard />

      {providersQuery.isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading providers…
        </div>
      ) : (
        grouped.map((group) => (
          <section key={group.label} className="space-y-3">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
              {group.label}
            </h2>
            <div className="space-y-2">
              {group.entries.map((entry) => (
                <ProviderCard key={entry.definition.id} entry={entry} />
              ))}
            </div>
          </section>
        ))
      )}
    </div>
  )
}
