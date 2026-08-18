/**
 * Entity inspector (BUILD_SPEC section 16): the right-side panel for any world
 * entity. Shows canonical name, type, current facts, relationships, related
 * tasks, memories, history, and provenance — everything with its source,
 * because section 46 treats external content as evidence, not authority.
 *
 * The panel never edits properties. The one write it offers is unlinking a
 * relationship, which is a domain operation in the world API, not free-form
 * graph editing (section 15).
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { History, Loader2, Unlink, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  LifeOpsError,
  TASK_STATE_LABELS,
  errorMessage,
  preferencesApi,
  relationshipsFrom,
  worldApi,
  worldTypeLabel,
  type WorldRelationshipView,
} from '@/services/lifeops'

function unlinkPayload(
  entityId: string,
  relationship: WorldRelationshipView,
): { source_id: string; target_id: string; rel_type: string } {
  // The edge is directed; the API identifies it by its (source, target, type)
  // triple, so an incoming relationship has to be sent the way it was stored.
  return relationship.direction === 'incoming'
    ? {
        source_id: relationship.otherId,
        target_id: entityId,
        rel_type: relationship.type,
      }
    : {
        source_id: entityId,
        target_id: relationship.otherId,
        rel_type: relationship.type,
      }
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-1.5">
      <h3 className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
        {title}
      </h3>
      {children}
    </section>
  )
}

function Empty({ children }: { children: string }) {
  return <p className="text-xs text-muted-foreground">{children}</p>
}

export function EntityInspector({
  entityId,
  viewMode = 'current',
  onClose,
  onNavigate,
  onGraphChanged,
}: {
  entityId: string
  /** Section 15's temporal/current toggle. Only a Preference entity has
   * anything to show in 'history' mode — see the note below Current facts. */
  viewMode?: 'current' | 'history'
  onClose: () => void
  onNavigate: (id: string) => void
  onGraphChanged: () => void
}) {
  const queryClient = useQueryClient()

  const detailQuery = useQuery({
    queryKey: ['lifeops', 'world', 'entity', entityId],
    queryFn: () => worldApi.entity(entityId),
  })

  const historyQuery = useQuery({
    queryKey: ['lifeops', 'world', 'history', entityId],
    queryFn: () => worldApi.history(entityId),
  })

  const isPreference = detailQuery.data?.entity.entity_type === 'preference'
  const preferenceKey = detailQuery.data?.entity.facts.key
  const preferenceHistoryQuery = useQuery({
    queryKey: ['lifeops', 'preferences', 'history', preferenceKey],
    queryFn: () => preferencesApi.history(preferenceKey as string),
    enabled: viewMode === 'history' && isPreference && Boolean(preferenceKey),
  })

  const unlink = useMutation({
    mutationFn: (relationship: WorldRelationshipView) =>
      worldApi.unlink(unlinkPayload(entityId, relationship)),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'world'] })
      onGraphChanged()
    },
  })

  if (detailQuery.isLoading) {
    return (
      <aside className="flex w-80 shrink-0 items-center gap-2 rounded-lg border border-border/60 bg-card p-4 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading entity…
      </aside>
    )
  }

  if (detailQuery.isError) {
    return (
      <aside className="w-80 shrink-0 rounded-lg border border-border/60 bg-card p-4">
        <p className="text-sm text-red-600">{errorMessage(detailQuery.error)}</p>
        <Button
          variant="outline"
          size="sm"
          className="mt-3"
          onClick={() => void detailQuery.refetch()}
        >
          Retry
        </Button>
      </aside>
    )
  }

  const detail = detailQuery.data
  if (!detail) return null

  const { entity } = detail
  const facts = Object.entries(entity.facts)
  const relationships = relationshipsFrom(entityId, detail)
  // Provenance is carried on the record itself rather than a parallel
  // structure (section 16): who recorded it, and when.
  const provenanceEntries: Array<[string, string]> = [
    ['recorded by', entity.created_by_client ?? 'unknown'],
    ['created', entity.created_at],
    ['updated', entity.updated_at],
  ].filter(([, value]) => value !== '') as Array<[string, string]>

  return (
    <aside
      aria-label={`Entity inspector: ${entity.display_name}`}
      className="w-80 shrink-0 space-y-5 overflow-y-auto rounded-lg border border-border/60 bg-card p-4"
    >
      <header className="flex items-start justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">{entity.display_name}</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {worldTypeLabel(entity.entity_type)}
          </p>
          <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">{entity.id}</p>
        </div>
        <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close inspector">
          <X className="h-4 w-4" />
        </Button>
      </header>

      {viewMode === 'history' && isPreference ? (
        <Section title="Preference history">
          {preferenceHistoryQuery.isLoading ? (
            <p className="flex items-center gap-1 text-xs text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" /> Loading history…
            </p>
          ) : preferenceHistoryQuery.isError ? (
            <p className="text-xs text-red-600">
              {errorMessage(preferenceHistoryQuery.error)}
            </p>
          ) : (preferenceHistoryQuery.data?.history ?? []).length === 0 ? (
            <Empty>No recorded history.</Empty>
          ) : (
            <ol className="space-y-1.5">
              {(preferenceHistoryQuery.data?.history ?? []).map((version) => (
                <li key={version.id} className="text-xs">
                  <span className="flex items-center gap-1 text-muted-foreground">
                    <History className="h-3 w-3" />
                    since {version.valid_from}
                    {version.valid_to !== null && ` · until ${version.valid_to}`}
                  </span>
                  <span
                    className={
                      version.valid_to !== null
                        ? 'text-sm text-muted-foreground line-through'
                        : 'text-sm font-medium'
                    }
                  >
                    {version.value}
                  </span>
                </li>
              ))}
            </ol>
          )}
        </Section>
      ) : (
        <Section title="Current facts">
          {facts.length === 0 ? (
            <Empty>No facts recorded.</Empty>
          ) : (
            <dl className="space-y-1">
              {facts.map(([key, value]) => (
                <div key={key} className="flex items-baseline justify-between gap-3 text-sm">
                  <dt className="shrink-0 text-muted-foreground">{key}</dt>
                  <dd className="truncate text-right">{value}</dd>
                </div>
              ))}
            </dl>
          )}
          {viewMode === 'history' && (
            <p className="text-[11px] italic text-muted-foreground">
              This entity type carries only current facts (BUILD_SPEC section
              40) — there is no per-fact history to show yet.
            </p>
          )}
        </Section>
      )}

      <Section title="Relationships">
        {relationships.length === 0 ? (
          <Empty>No relationships.</Empty>
        ) : (
          <ul className="space-y-1">
            {relationships.map((relationship) => (
              <li
                key={`${relationship.direction}|${relationship.type}|${relationship.otherId}`}
                className="flex items-center gap-2 text-sm"
              >
                <span className="text-muted-foreground">
                  {relationship.direction === 'incoming' ? '←' : '→'}
                </span>
                <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium">
                  {relationship.type}
                </span>
                <button
                  type="button"
                  className="truncate text-left hover:underline"
                  onClick={() => onNavigate(relationship.otherId)}
                >
                  {relationship.otherLabel}
                </button>
                <button
                  type="button"
                  aria-label={`Remove ${relationship.type} relationship with ${relationship.otherLabel}`}
                  className="ml-auto text-muted-foreground hover:text-red-600"
                  disabled={unlink.isPending}
                  onClick={() => unlink.mutate(relationship)}
                >
                  <Unlink className="h-3.5 w-3.5" />
                </button>
              </li>
            ))}
          </ul>
        )}
        {unlink.isError && (
          <p className="text-xs text-red-600">
            {unlink.error instanceof LifeOpsError
              ? unlink.error.message
              : 'Could not remove the relationship.'}
          </p>
        )}
      </Section>

      <Section title="Related tasks">
        {detail.related_tasks.length === 0 ? (
          <Empty>No related tasks.</Empty>
        ) : (
          <ul className="space-y-1">
            {detail.related_tasks.map((task) => (
              <li key={task.id} className="text-sm">
                {task.title}
                <span className="ml-2 text-xs text-muted-foreground">
                  {TASK_STATE_LABELS[task.state]}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Memories">
        {detail.related_memories.length === 0 ? (
          <Empty>No related memories.</Empty>
        ) : (
          <ul className="space-y-1">
            {detail.related_memories.map((memory) => (
              <li
                key={memory.id}
                className={
                  memory.valid_to !== null
                    ? 'text-sm text-muted-foreground line-through'
                    : 'text-sm'
                }
              >
                {memory.content}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="History">
        {historyQuery.isLoading ? (
          <p className="flex items-center gap-1 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" /> Loading history…
          </p>
        ) : historyQuery.isError ? (
          <p className="text-xs text-red-600">{errorMessage(historyQuery.error)}</p>
        ) : (historyQuery.data?.memories ?? []).length === 0 ? (
          <Empty>No recorded changes.</Empty>
        ) : (
          <ol className="space-y-1.5">
            {(historyQuery.data?.memories ?? []).map((memory) => (
              <li key={memory.id} className="text-xs">
                <span className="flex items-center gap-1 text-muted-foreground">
                  <History className="h-3 w-3" />
                  {memory.created_at}
                  {memory.valid_to !== null && ' · no longer current'}
                </span>
                <span
                  className={
                    memory.valid_to !== null
                      ? 'text-sm text-muted-foreground line-through'
                      : 'text-sm'
                  }
                >
                  {memory.content}
                </span>
              </li>
            ))}
          </ol>
        )}
        {/* The server states its own scope, so an empty list is never
            mistaken for "nothing ever happened". */}
        {(historyQuery.data?.covers ?? []).map((note) => (
          <p key={note} className="text-[11px] italic text-muted-foreground">
            Covers {note}.
          </p>
        ))}
      </Section>

      <Section title="Provenance">
        {provenanceEntries.length === 0 ? (
          <Empty>No provenance recorded.</Empty>
        ) : (
          <dl className="space-y-1">
            {provenanceEntries.map(([key, value]) => (
              <div key={key} className="flex items-baseline justify-between gap-3 text-xs">
                <dt className="shrink-0 text-muted-foreground">{key}</dt>
                <dd className="truncate text-right font-mono">{String(value)}</dd>
              </div>
            ))}
          </dl>
        )}
      </Section>
    </aside>
  )
}
