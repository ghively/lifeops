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
  type ProviderEntry,
  type ProviderField,
  type ProviderState,
} from '@/services/lifeops'

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
