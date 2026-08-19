/**
 * Hermes — the personal assistant behind LifeOps (BUILD_SPEC section 20).
 *
 * "Do not reproduce a second agent platform." This screen shows what LifeOps
 * Core actually knows about Hermes and nothing invented on top of it:
 *
 *  - Model and connection state come from `/system/status`'s provider list
 *    and `/voice/mode-status` — real config, read honestly (a provider with
 *    no configured model shows that, not a placeholder value).
 *  - "Online/offline" has no real backing: there is no MCP connection
 *    registry anywhere in LifeOps Core (no heartbeat, no last-seen-per-client
 *    table), so this screen shows *last recorded activity* instead — a
 *    literal timestamp from the audit log, not a guess dressed up as a
 *    presence indicator.
 *  - Recent actions reuse the audit log's narrative builder from the
 *    Activity screen (`narrateAudit`/`clientLabel`), filtered to Hermes,
 *    rather than a second retelling of the same vocabulary.
 *  - Routines reuse `workflowTemplatesApi` — summarized here, fully managed
 *    on the Routines screen — per the spec's "do not rebuild a separate
 *    scheduling platform."
 *  - MCP status, memory-provider status, and active skills have no backing
 *    data at all right now (no connection registry, no separate memory
 *    provider by design, zero skills instantiated) and say so plainly
 *    instead of fabricating a state. The spec's "optional embedded
 *    conversation panel" is skipped entirely — there is no chat endpoint in
 *    LifeOps Core to back it, and the spec marks it optional.
 */

import { useQuery } from '@tanstack/react-query'
import { Bot, Loader2, Repeat } from 'lucide-react'
import { Link } from 'react-router-dom'

import { QueryError } from '@/components/QueryError'
import { cn } from '@/lib/utils'
import {
  PROVIDER_STATE_LABELS,
  auditApi,
  errorMessage,
  systemApi,
  voiceApi,
  workflowTemplatesApi,
  type AuditRecord,
  type ProviderStatus,
} from '@/services/lifeops'
import { clientLabel, formatTime, narrateAudit } from './ActivityPage'

const HERMES_CLIENT_ID = 'hermes-personal'

function StatusBadge({ label, tone }: { label: string; tone: 'ok' | 'warn' | 'muted' }) {
  return (
    <span
      className={cn(
        'rounded-full px-2 py-0.5 text-xs font-medium',
        tone === 'ok' && 'bg-green-100 text-green-800',
        tone === 'warn' && 'bg-amber-100 text-amber-800',
        tone === 'muted' && 'bg-muted text-muted-foreground',
      )}
    >
      {label}
    </span>
  )
}

function providerTone(state: ProviderStatus['state']): 'ok' | 'warn' | 'muted' {
  if (state === 'healthy' || state === 'configured') return 'ok'
  if (state === 'unhealthy') return 'warn'
  return 'muted'
}

function ProviderRow({
  label,
  provider,
  detail,
}: {
  label: string
  provider: ProviderStatus | undefined
  detail?: string
}) {
  return (
    <div className="flex items-center justify-between gap-4 px-4 py-2.5 text-sm">
      <div className="min-w-0">
        <p>{label}</p>
        {detail && <p className="text-xs text-muted-foreground">{detail}</p>}
      </div>
      {provider ? (
        <StatusBadge
          label={PROVIDER_STATE_LABELS[provider.state]}
          tone={providerTone(provider.state)}
        />
      ) : (
        <StatusBadge label="Not configured" tone="muted" />
      )}
    </div>
  )
}

function NotTrackedRow({ label, reason }: { label: string; reason: string }) {
  return (
    <div className="px-4 py-2.5 text-sm">
      <div className="flex items-center justify-between gap-4">
        <p>{label}</p>
        <StatusBadge label="Not tracked" tone="muted" />
      </div>
      <p className="mt-0.5 text-xs text-muted-foreground">{reason}</p>
    </div>
  )
}

function RecentActionRow({ record }: { record: AuditRecord }) {
  const failed =
    record.result.includes('fail') ||
    record.result.includes('denied') ||
    record.result.includes('error')
  return (
    <div className="flex items-start justify-between gap-4 rounded-lg border border-border/60 px-4 py-2.5 text-sm">
      <span className={cn(failed && 'text-red-600')}>{narrateAudit(record)}</span>
      <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
        {formatTime(record.timestamp)}
      </span>
    </div>
  )
}

export function HermesPage() {
  const statusQuery = useQuery({
    queryKey: ['lifeops', 'system-status'],
    queryFn: systemApi.status,
    refetchInterval: 20_000,
  })

  const voiceQuery = useQuery({
    queryKey: ['lifeops', 'voice', 'mode-status'],
    queryFn: voiceApi.getModeStatus,
    retry: false,
  })

  const auditQuery = useQuery({
    queryKey: ['lifeops', 'audit', 'hermes'],
    queryFn: () => auditApi.read({ limit: 200 }),
    refetchInterval: 30_000,
  })

  const activityQuery = useQuery({
    queryKey: ['lifeops', 'activity'],
    queryFn: systemApi.getActivity,
    refetchInterval: 15_000,
  })

  const routinesQuery = useQuery({
    queryKey: ['lifeops', 'workflow-templates'],
    queryFn: () => workflowTemplatesApi.list({ limit: 200 }),
  })

  if (statusQuery.isError) {
    return (
      <div className="p-8">
        <QueryError
          message={errorMessage(statusQuery.error)}
          onRetry={() => void statusQuery.refetch()}
        />
      </div>
    )
  }

  const status = statusQuery.data
  const providers = status?.providers ?? []
  const llmProvider = providers.find((p) => p.category === 'llm')
  const voiceTts = providers.find((p) => p.category === 'voice_tts' && p.id === voiceQuery.data?.tts_active)
  const voiceAsr = providers.find((p) => p.category === 'voice_asr' && p.id === voiceQuery.data?.asr_active)
  const telegram = providers.find((p) => p.id === 'telegram')

  const hermesAudit = (auditQuery.data?.records ?? []).filter(
    (record) => record.client === HERMES_CLIENT_ID,
  )
  const hermesActivity = (activityQuery.data ?? []).filter(
    (entry) => entry.client_id === HERMES_CLIENT_ID,
  )
  const lastAuditAt = hermesAudit[0]?.timestamp ?? null
  const lastActivityAt = hermesActivity
    .map((e) => e.ts)
    .sort((a, b) => new Date(b).getTime() - new Date(a).getTime())[0] ?? null
  const lastSeenAt = [lastAuditAt, lastActivityAt]
    .filter((ts): ts is string => ts !== null)
    .sort((a, b) => new Date(b).getTime() - new Date(a).getTime())[0] ?? null

  const routines = routinesQuery.data?.templates ?? []
  const enabledRoutines = routines.filter((r) => r.enabled)

  return (
    <div className="mx-auto max-w-3xl space-y-8 p-8">
      <header>
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <Bot className="h-5 w-5" />
          Hermes
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          The personal assistant behind LifeOps.
        </p>
        <p className="mt-2 text-xs text-muted-foreground">
          {lastSeenAt
            ? `Last recorded activity ${formatTime(lastSeenAt)}.`
            : 'No activity recorded from Hermes yet.'}{' '}
          LifeOps Core has no live connection registry for MCP clients, so this
          is the most recent thing it recorded — not a real-time presence
          check.
        </p>
      </header>

      {statusQuery.isLoading || !status ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Checking…
        </div>
      ) : (
        <>
          <section className="space-y-3">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
              Model
            </h2>
            <div className="divide-y divide-border/60 rounded-lg border border-border/60">
              <ProviderRow
                label={llmProvider ? llmProvider.display_name : 'Primary model provider'}
                provider={llmProvider}
              />
              <div className="flex items-center justify-between gap-4 px-4 py-2.5 text-sm">
                <p>Current model</p>
                <p className="text-muted-foreground">
                  {typeof llmProvider?.settings.model === 'string' && llmProvider.settings.model
                    ? llmProvider.settings.model
                    : 'No model selected'}
                </p>
              </div>
            </div>
          </section>

          <section className="space-y-3">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
              Connections
            </h2>
            <div className="divide-y divide-border/60 rounded-lg border border-border/60">
              <NotTrackedRow
                label="LifeOps MCP"
                reason="LifeOps Core does not keep a connection registry for MCP clients — the audit log is the only record of what Hermes has done."
              />
              <NotTrackedRow
                label="Memory provider"
                reason="Memory is LifeOps Core's own durable store, not a swappable provider — there is nothing separate to report status for."
              />
              <ProviderRow
                label="Voice (text-to-speech)"
                provider={voiceTts}
                detail={voiceQuery.data ? `mode: ${voiceQuery.data.mode}` : undefined}
              />
              <ProviderRow label="Voice (speech-to-text)" provider={voiceAsr} />
              <ProviderRow label="Telegram" provider={telegram} />
            </div>
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                Routines
              </h2>
              <Link to="/routines" className="text-xs text-muted-foreground hover:underline">
                Manage on Routines
              </Link>
            </div>
            {routinesQuery.isLoading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading…
              </div>
            ) : routines.length === 0 ? (
              <p className="rounded-lg border border-dashed border-border/60 px-4 py-6 text-center text-sm text-muted-foreground">
                No routines yet.
              </p>
            ) : (
              <div className="rounded-lg border border-border/60 px-4 py-3 text-sm">
                <p className="flex items-center gap-1.5">
                  <Repeat className="h-3.5 w-3.5 text-muted-foreground" />
                  {enabledRoutines.length} of {routines.length}{' '}
                  {routines.length === 1 ? 'routine' : 'routines'} enabled
                </p>
              </div>
            )}
          </section>

          <section className="space-y-3">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
              Skills
            </h2>
            <p className="rounded-lg border border-dashed border-border/60 px-4 py-6 text-center text-sm text-muted-foreground">
              Nine LifeOps skills ship in this repository under
              hermes/skills/lifeops/ (personal-core, daily-brief,
              weekly-review, and more) and are installed with Hermes itself —
              see HERMES_INTEGRATION.md. Skill *content* is written there,
              not from this screen: over MCP, propose_self_change only files
              a request for review.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
              Recent actions
            </h2>
            {auditQuery.isLoading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading…
              </div>
            ) : hermesAudit.length === 0 ? (
              <p className="rounded-lg border border-dashed border-border/60 px-4 py-6 text-center text-sm text-muted-foreground">
                No recent actions recorded from Hermes.
              </p>
            ) : (
              <div className="space-y-2">
                {hermesAudit.slice(0, 10).map((record) => (
                  <RecentActionRow key={record.id} record={record} />
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  )
}
