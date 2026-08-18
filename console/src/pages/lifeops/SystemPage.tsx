/**
 * System health (BUILD_SPEC section 77).
 *
 * Shows overall API health, component health, provider state, this console's
 * resolved client identity, and every client's permissions. Deliberately
 * offers no arbitrary shell execution — the spec rules that out, and a health
 * screen is exactly where such a thing would look reasonable.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Activity, AlertTriangle, Loader2, RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { QueryError } from '@/components/QueryError'
import { cn } from '@/lib/utils'
import {
  PROVIDER_STATE_LABELS,
  configApi,
  errorMessage,
  systemApi,
  type ComponentHealth,
  type SystemStatus,
} from '@/services/lifeops'

const COMPONENT_LABELS: Record<string, string> = {
  lifeops_core: 'LifeOps Core',
  nornicdb: 'NornicDB',
  secret_store: 'Secret store',
}

function isHealth(value: unknown): value is ComponentHealth {
  return typeof value === 'object' && value !== null && 'healthy' in value
}

type ClientGrant = SystemStatus['clients'][number]

function ClientCard({ client }: { client: ClientGrant }) {
  return (
    <div className="rounded-lg border border-border/60 px-4 py-3">
      <div className="flex items-center justify-between">
        <p className="font-medium">{client.display_name}</p>
        <code className="text-xs text-muted-foreground">{client.client_id}</code>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">{client.description}</p>
      <div className="mt-2 flex flex-wrap gap-1">
        {client.capabilities.map((capability) => (
          <span
            key={capability}
            className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground"
          >
            {capability}
          </span>
        ))}
      </div>
    </div>
  )
}

export function SystemPage() {
  const queryClient = useQueryClient()

  const statusQuery = useQuery({
    queryKey: ['lifeops', 'system-status'],
    queryFn: systemApi.status,
    refetchInterval: 20_000,
  })

  // Lighter-weight liveness signal (GET /health) alongside the full status.
  const healthQuery = useQuery({
    queryKey: ['lifeops', 'system-health'],
    queryFn: systemApi.health,
    refetchInterval: 20_000,
  })

  const setSafeMode = useMutation({
    mutationFn: (safe_mode: boolean) => configApi.updateSystem({ safe_mode }),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'system-status'] }),
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
  const safeMode = status?.components.safe_mode === true

  return (
    <div className="mx-auto max-w-3xl space-y-8 p-8">
      <header className="flex items-start justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <Activity className="h-5 w-5" />
            System
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Component health and connected clients.
          </p>
          {healthQuery.data && (
            <p
              className={cn(
                'mt-2 inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium',
                healthQuery.data.status === 'ok'
                  ? 'bg-green-100 text-green-800'
                  : 'bg-red-100 text-red-800',
              )}
            >
              {healthQuery.data.status === 'ok'
                ? 'LifeOps Core is healthy'
                : 'LifeOps Core reports a problem'}
            </p>
          )}
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            void statusQuery.refetch()
            void healthQuery.refetch()
          }}
          disabled={statusQuery.isFetching}
        >
          <RefreshCw
            className={cn('h-3.5 w-3.5', statusQuery.isFetching && 'animate-spin')}
          />
          <span className="ml-1">Refresh</span>
        </Button>
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
              Components
            </h2>
            <div className="divide-y divide-border/60 rounded-lg border border-border/60">
              {Object.entries(status.components)
                .filter(([, value]) => isHealth(value))
                .map(([key, value]) => {
                  const health = value as ComponentHealth
                  return (
                    <div
                      key={key}
                      className="flex items-center justify-between px-4 py-3"
                    >
                      <div>
                        <p className="font-medium">{COMPONENT_LABELS[key] ?? key}</p>
                        <p className="text-xs text-muted-foreground">{health.detail}</p>
                      </div>
                      <span
                        className={cn(
                          'rounded-full px-2 py-0.5 text-xs font-medium',
                          health.healthy
                            ? 'bg-green-100 text-green-800'
                            : 'bg-red-100 text-red-800',
                        )}
                      >
                        {health.healthy ? 'Healthy' : 'Unreachable'}
                      </span>
                    </div>
                  )
                })}
            </div>
          </section>

          <section className="space-y-3">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
              Providers
            </h2>
            <div className="divide-y divide-border/60 rounded-lg border border-border/60">
              {status.providers.map((provider) => (
                <div
                  key={provider.id}
                  className="flex items-center justify-between px-4 py-2.5 text-sm"
                >
                  <span>{provider.display_name}</span>
                  <span className="text-muted-foreground">
                    {PROVIDER_STATE_LABELS[provider.state]}
                  </span>
                </div>
              ))}
            </div>
          </section>

          <section className="space-y-3">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
              This console
            </h2>
            <p className="text-sm text-muted-foreground">
              The identity LifeOps resolved for this Console session and what it
              is permitted to do.
            </p>
            <ClientCard client={status.requesting_client} />
          </section>

          <section className="space-y-3">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
              Client access
            </h2>
            <p className="text-sm text-muted-foreground">
              What each connected client is permitted to do. LifeOps enforces
              this server-side; a client cannot grant itself more.
            </p>
            <div className="space-y-2">
              {status.clients.map((client) => (
                <ClientCard key={client.client_id} client={client} />
              ))}
            </div>
          </section>

          <section className="space-y-3">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
              Emergency stop
            </h2>
            <p className="text-sm text-muted-foreground">
              Stops external writes, bookings, shopping submission, telephony,
              and financial actions immediately (BUILD_SPEC section 84).
              Nothing is deleted: state, logs, the audit trail, the database,
              and every previously prepared action are preserved exactly as
              they were.
            </p>
            <div
              className={cn(
                'flex items-start justify-between gap-4 rounded-lg border px-4 py-3',
                safeMode ? 'border-amber-400 bg-amber-50' : 'border-border/60',
              )}
            >
              <div className="flex items-start gap-2">
                <AlertTriangle
                  className={cn(
                    'mt-0.5 h-4 w-4 shrink-0',
                    safeMode ? 'text-amber-600' : 'text-muted-foreground',
                  )}
                />
                <div>
                  <p className="text-sm font-medium">
                    {safeMode ? 'Safe mode is on' : 'Safe mode is off'}
                  </p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    Blocks external communication, bookings, browser writes,
                    shopping submission, telephony writes, and payments
                    (BUILD_SPEC section 83). Conversation, reads, memory
                    search, tasks, local state, and this Console keep working.
                    The setting is stored in LifeOps configuration, so it
                    survives a restart — it is not just a process flag.
                  </p>
                </div>
              </div>
              <Button
                variant={safeMode ? 'default' : 'outline'}
                size="sm"
                className="shrink-0"
                disabled={setSafeMode.isPending}
                onClick={() => setSafeMode.mutate(!safeMode)}
              >
                {setSafeMode.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : safeMode ? (
                  'Turn off'
                ) : (
                  'Turn on'
                )}
              </Button>
            </div>
          </section>
        </>
      )}
    </div>
  )
}
