/**
 * Memory — persistent assistant memory, made inspectable and correctable
 * (BUILD_SPEC section 17).
 *
 * Every record carries full provenance (source, confidence, validity window)
 * because section 46 says external content is evidence, not authority — the
 * user has to be able to see *why* the assistant believes something before
 * they can judge it. Correction is supersession and invalidation closes a
 * validity window; nothing here edits a record in place or touches
 * transactional state (section 44).
 *
 * Section 17 names seven views (Preferences, Personal facts, Relationships,
 * Episodic memories, Semantic memories, Procedures/routines, Invalidated/
 * superseded history). This screen implements six of them — "Personal facts"
 * and "Semantic memories" both point at the one `semantic` MemoryType, so
 * they collapse to a single view rather than showing the same records twice
 * under two names. "Preferences" is the one view backed by a different
 * domain entirely (Preference, not Memory) — it gets its own query and its
 * own lightweight card/detail pair rather than being forced into the
 * MemoryRecord shape it doesn't have.
 */

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Brain, CheckCircle2, History, Loader2, Pencil, Search, XCircle } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { QueryError } from '@/components/QueryError'
import { cn } from '@/lib/utils'
import {
  LifeOpsError,
  MEMORY_SOURCE_LABELS,
  MEMORY_TYPE_LABELS,
  errorMessage,
  memoryApi,
  preferencesApi,
  type MemoryRecord,
  type MemoryType,
  type Preference,
} from '@/services/lifeops'

type ViewId =
  | 'all'
  | 'preferences'
  | 'personal_facts'
  | 'relationships'
  | 'episodic'
  | 'procedures'
  | 'invalidated'

const VIEWS: Array<{ id: ViewId; label: string }> = [
  { id: 'all', label: 'All' },
  { id: 'preferences', label: 'Preferences' },
  { id: 'personal_facts', label: 'Personal facts' },
  { id: 'relationships', label: 'Relationships' },
  { id: 'episodic', label: 'Episodic memories' },
  { id: 'procedures', label: 'Procedures/routines' },
  { id: 'invalidated', label: 'Invalidated/superseded history' },
]

/** The MemoryType each view maps to, where it maps to exactly one. */
const VIEW_MEMORY_TYPE: Partial<Record<ViewId, MemoryType>> = {
  personal_facts: 'semantic',
  relationships: 'association',
  episodic: 'episodic',
  procedures: 'summary',
}

const SOURCE_FILTERS: Array<{ id: string; label: string }> = [
  { id: 'all', label: 'Any source' },
  ...Object.entries(MEMORY_SOURCE_LABELS).map(([id, label]) => ({ id, label })),
]

function sourceLabel(sourceType: string): string {
  return MEMORY_SOURCE_LABELS[sourceType] ?? sourceType
}

function MemoryCard({
  memory,
  selected,
  onSelect,
}: {
  memory: MemoryRecord
  selected: boolean
  onSelect: () => void
}) {
  const invalidated = memory.valid_to !== null
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={cn(
        'w-full rounded-lg border border-border/60 bg-card px-4 py-3 text-left transition-colors',
        selected ? 'border-foreground' : 'hover:bg-muted/40',
      )}
    >
      <p
        className={cn(
          'text-sm font-medium',
          invalidated && 'text-muted-foreground line-through',
        )}
      >
        {memory.content}
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        <span>{MEMORY_TYPE_LABELS[memory.type]}</span>
        <span>{sourceLabel(memory.source_type)}</span>
        <span>confidence {memory.confidence.toFixed(2)}</span>
        {invalidated && <span className="text-red-500">invalidated</span>}
        {memory.supersedes && <span>supersedes an earlier record</span>}
      </div>
    </button>
  )
}

function ProvenanceRow({ label, value }: { label: string; value: string | null }) {
  if (!value) return null
  return (
    <div className="flex items-baseline justify-between gap-4 text-sm">
      <span className="shrink-0 text-muted-foreground">{label}</span>
      <span className="truncate text-right font-mono text-xs">{value}</span>
    </div>
  )
}

function MemoryDetail({
  memory,
  onChanged,
}: {
  memory: MemoryRecord
  onChanged: (next: MemoryRecord) => void
}) {
  const queryClient = useQueryClient()
  const [mode, setMode] = useState<'none' | 'correct' | 'invalidate' | 'promote'>('none')
  const [draft, setDraft] = useState('')
  const [promoteKey, setPromoteKey] = useState('')
  const [promoteValue, setPromoteValue] = useState('')
  const [actionError, setActionError] = useState<string | null>(null)

  const historyQuery = useQuery({
    queryKey: ['lifeops', 'memory', 'history', memory.id],
    queryFn: () => memoryApi.history(memory.id),
  })

  const correct = useMutation({
    mutationFn: (content: string) => memoryApi.correct(memory.id, content),
    onSuccess: (next) => {
      setMode('none')
      setDraft('')
      setActionError(null)
      onChanged(next)
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'memory'] })
    },
    onError: (error) => {
      // The server refusing a correction (filler, secret-like content) is
      // information the user needs, not a failure to hide.
      setActionError(
        error instanceof LifeOpsError ? error.message : 'Could not correct the memory.',
      )
    },
  })

  const invalidate = useMutation({
    mutationFn: (reason: string) => memoryApi.invalidate(memory.id, reason),
    onSuccess: (next) => {
      setMode('none')
      setDraft('')
      setActionError(null)
      onChanged(next)
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'memory'] })
    },
    onError: (error) => {
      setActionError(
        error instanceof LifeOpsError ? error.message : 'Could not invalidate the memory.',
      )
    },
  })

  const promote = useMutation({
    mutationFn: () => memoryApi.promote(memory.id, promoteKey.trim(), promoteValue.trim() || undefined),
    onSuccess: async () => {
      setMode('none')
      setPromoteKey('')
      setPromoteValue('')
      setActionError(null)
      // Promotion closes the candidate's validity window as a side effect —
      // refetch it rather than guessing the new shape.
      onChanged(await memoryApi.get(memory.id))
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'memory'] })
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'preferences'] })
    },
    onError: (error) => {
      setActionError(
        error instanceof LifeOpsError ? error.message : 'Could not promote the memory.',
      )
    },
  })

  const pending = correct.isPending || invalidate.isPending || promote.isPending
  const invalidated = memory.valid_to !== null
  const isCandidate = memory.type === 'preference_candidate'

  return (
    <section
      aria-label={`Memory detail: ${memory.content}`}
      className="space-y-4 rounded-lg border border-border/60 bg-card px-4 py-4"
    >
      <div>
        <p className="text-sm font-medium">{memory.content}</p>
        <p className="mt-1 text-xs text-muted-foreground">
          {MEMORY_TYPE_LABELS[memory.type]} · {memory.id}
        </p>
      </div>

      <div className="space-y-1 rounded-md border border-border/40 bg-muted/30 px-3 py-2">
        <ProvenanceRow label="Source" value={sourceLabel(memory.source_type)} />
        <ProvenanceRow label="Source reference" value={memory.source_id} />
        <ProvenanceRow label="Observed" value={memory.observed_at} />
        <ProvenanceRow label="Recorded" value={memory.created_at} />
        <ProvenanceRow label="Valid from" value={memory.valid_from} />
        <ProvenanceRow label="Valid until" value={memory.valid_to} />
        <ProvenanceRow label="Supersedes" value={memory.supersedes} />
        <ProvenanceRow label="Recorded by" value={memory.created_by_client} />
        <ProvenanceRow
          label="Related entities"
          value={memory.entity_ids.length > 0 ? memory.entity_ids.join(', ') : null}
        />
        <ProvenanceRow label="Invalidation reason" value={memory.invalidation_reason} />
        <ProvenanceRow
          label="Confidence / importance"
          value={`${memory.confidence.toFixed(2)} / ${memory.importance.toFixed(2)}`}
        />
      </div>

      {!invalidated && mode === 'none' && (
        <div className="flex flex-wrap gap-2">
          {isCandidate && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setMode('promote')
                setPromoteKey('')
                setPromoteValue(memory.content)
                setActionError(null)
              }}
            >
              <CheckCircle2 className="mr-1 h-3 w-3" />
              Promote to preference
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setMode('correct')
              setDraft(memory.content)
              setActionError(null)
            }}
          >
            <Pencil className="mr-1 h-3 w-3" />
            Correct
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setMode('invalidate')
              setDraft('')
              setActionError(null)
            }}
          >
            <XCircle className="mr-1 h-3 w-3" />
            Invalidate
          </Button>
        </div>
      )}

      {mode === 'promote' && (
        <form
          className="space-y-2"
          onSubmit={(event) => {
            event.preventDefault()
            if (promoteKey.trim()) promote.mutate()
          }}
        >
          <Input
            value={promoteKey}
            onChange={(event) => setPromoteKey(event.target.value)}
            placeholder="Preference key, e.g. scheduling.earliest_appointment_time"
            aria-label="Preference key"
            disabled={pending}
          />
          <Input
            value={promoteValue}
            onChange={(event) => setPromoteValue(event.target.value)}
            aria-label="Preference value"
            disabled={pending}
          />
          <p className="text-xs text-muted-foreground">
            This is a hypothesis until confirmed (§47) — promoting it records a
            real preference with your explicit authority and closes this
            candidate out.
          </p>
          <div className="flex gap-2">
            <Button type="submit" size="sm" disabled={!promoteKey.trim() || pending}>
              {pending ? <Loader2 className="h-3 w-3 animate-spin" /> : 'Promote'}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setMode('none')}
              disabled={pending}
            >
              Cancel
            </Button>
          </div>
        </form>
      )}

      {mode === 'correct' && (
        <form
          className="space-y-2"
          onSubmit={(event) => {
            event.preventDefault()
            const content = draft.trim()
            if (content) correct.mutate(content)
          }}
        >
          <Input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            aria-label="Corrected memory content"
            disabled={pending}
          />
          <p className="text-xs text-muted-foreground">
            Correction never edits the record: the old version closes and a new
            one supersedes it, so the history stays answerable.
          </p>
          <div className="flex gap-2">
            <Button type="submit" size="sm" disabled={!draft.trim() || pending}>
              {pending ? <Loader2 className="h-3 w-3 animate-spin" /> : 'Save correction'}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setMode('none')}
              disabled={pending}
            >
              Cancel
            </Button>
          </div>
        </form>
      )}

      {mode === 'invalidate' && (
        <form
          className="space-y-2"
          onSubmit={(event) => {
            event.preventDefault()
            const reason = draft.trim()
            if (reason) invalidate.mutate(reason)
          }}
        >
          <Input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Why is this no longer true?"
            aria-label="Invalidation reason"
            disabled={pending}
          />
          <p className="text-xs text-muted-foreground">
            Invalidation closes the validity window. The record is never deleted.
          </p>
          <div className="flex gap-2">
            <Button type="submit" size="sm" disabled={!draft.trim() || pending}>
              {pending ? <Loader2 className="h-3 w-3 animate-spin" /> : 'Invalidate'}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setMode('none')}
              disabled={pending}
            >
              Cancel
            </Button>
          </div>
        </form>
      )}

      {actionError && (
        <p className="rounded border border-red-300 bg-red-50 px-2 py-1 text-xs text-red-700">
          {actionError}
        </p>
      )}

      <div>
        <p className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
          <History className="h-3 w-3" />
          History
        </p>
        {historyQuery.isLoading ? (
          <p className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" /> Loading history…
          </p>
        ) : historyQuery.isError ? (
          <p className="mt-1 text-xs text-red-600">{errorMessage(historyQuery.error)}</p>
        ) : (
          <ol className="mt-2 space-y-1">
            {(historyQuery.data?.history ?? []).map((entry) => (
              <li
                key={entry.id}
                className={cn(
                  'rounded border border-border/40 px-2 py-1 text-xs',
                  entry.valid_to !== null && 'text-muted-foreground line-through',
                )}
              >
                {entry.content}
                <span className="ml-2 text-muted-foreground no-underline">
                  {entry.id === memory.id ? 'current view' : entry.valid_to ? 'closed' : 'current'}
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  )
}

function PreferenceCard({
  preference,
  selected,
  onSelect,
}: {
  preference: Preference
  selected: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={cn(
        'w-full rounded-lg border border-border/60 bg-card px-4 py-3 text-left transition-colors',
        selected ? 'border-foreground' : 'hover:bg-muted/40',
      )}
    >
      <p className="text-sm font-medium">{preference.key}</p>
      <p className="mt-1 text-sm text-muted-foreground">{preference.value}</p>
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        <span>{sourceLabel(preference.source_type)}</span>
        <span>confidence {preference.confidence.toFixed(2)}</span>
      </div>
    </button>
  )
}

function PreferenceDetail({
  preference,
  onChanged,
}: {
  preference: Preference
  onChanged: (next: Preference | null) => void
}) {
  const queryClient = useQueryClient()
  const [mode, setMode] = useState<'none' | 'restate'>('none')
  const [draft, setDraft] = useState('')
  const [actionError, setActionError] = useState<string | null>(null)

  const restate = useMutation({
    mutationFn: (value: string) => preferencesApi.save({ key: preference.key, value }),
    onSuccess: (next) => {
      setMode('none')
      setDraft('')
      setActionError(null)
      onChanged(next)
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'preferences'] })
    },
    onError: (error) => {
      setActionError(
        error instanceof LifeOpsError ? error.message : 'Could not save the preference.',
      )
    },
  })

  const invalidate = useMutation({
    mutationFn: () => preferencesApi.invalidate(preference.id),
    onSuccess: () => {
      setActionError(null)
      onChanged(null)
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'preferences'] })
    },
    onError: (error) => {
      setActionError(
        error instanceof LifeOpsError ? error.message : 'Could not invalidate the preference.',
      )
    },
  })

  const pending = restate.isPending || invalidate.isPending

  return (
    <section
      aria-label={`Preference detail: ${preference.key}`}
      className="space-y-4 rounded-lg border border-border/60 bg-card px-4 py-4"
    >
      <div>
        <p className="text-sm font-medium">{preference.key}</p>
        <p className="mt-1 text-sm text-muted-foreground">{preference.value}</p>
      </div>

      <div className="space-y-1 rounded-md border border-border/40 bg-muted/30 px-3 py-2">
        <ProvenanceRow label="Source" value={sourceLabel(preference.source_type)} />
        <ProvenanceRow label="Source reference" value={preference.source_id} />
        <ProvenanceRow label="Observed" value={preference.observed_at} />
        <ProvenanceRow label="Valid from" value={preference.valid_from} />
        <ProvenanceRow label="Supersedes" value={preference.supersedes} />
        <ProvenanceRow label="Recorded by" value={preference.created_by_client} />
        <ProvenanceRow
          label="Confidence / importance"
          value={`${preference.confidence.toFixed(2)} / ${preference.importance.toFixed(2)}`}
        />
      </div>

      {mode === 'none' && (
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setMode('restate')
              setDraft(preference.value)
              setActionError(null)
            }}
          >
            <Pencil className="mr-1 h-3 w-3" />
            Correct / supersede
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => invalidate.mutate()}
            disabled={pending}
          >
            <XCircle className="mr-1 h-3 w-3" />
            Invalidate
          </Button>
        </div>
      )}

      {mode === 'restate' && (
        <form
          className="space-y-2"
          onSubmit={(event) => {
            event.preventDefault()
            const value = draft.trim()
            if (value) restate.mutate(value)
          }}
        >
          <Input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            aria-label="Corrected preference value"
            disabled={pending}
          />
          <p className="text-xs text-muted-foreground">
            Saving a new value for {preference.key} supersedes this one — the old
            version closes and stays queryable in the World screen's history view.
          </p>
          <div className="flex gap-2">
            <Button type="submit" size="sm" disabled={!draft.trim() || pending}>
              {pending ? <Loader2 className="h-3 w-3 animate-spin" /> : 'Save'}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setMode('none')}
              disabled={pending}
            >
              Cancel
            </Button>
          </div>
        </form>
      )}

      {actionError && (
        <p className="rounded border border-red-300 bg-red-50 px-2 py-1 text-xs text-red-700">
          {actionError}
        </p>
      )}
    </section>
  )
}

export function MemoryPage() {
  const [query, setQuery] = useState('')
  const [view, setView] = useState<ViewId>('all')
  const [sourceFilter, setSourceFilter] = useState('all')
  const [selected, setSelected] = useState<MemoryRecord | null>(null)
  const [selectedPreference, setSelectedPreference] = useState<Preference | null>(null)

  const trimmedQuery = query.trim()
  // Preferences have no search integration here (they have no search
  // endpoint of their own in this screen) — free text only ever narrows the
  // memory views, so it's disabled while "Preferences" is active. The
  // invalidated view never switches to server search either: recall covers
  // *current* records only, so searching there showed current memories
  // under the "Invalidated" chip — the opposite of what the view promises
  // (2026-08-18 audit). It filters the listed history locally instead.
  const searching =
    trimmedQuery.length > 0 && view !== 'preferences' && view !== 'invalidated'

  const listQuery = useQuery({
    queryKey: ['lifeops', 'memory', 'list', view],
    queryFn: () =>
      memoryApi.list({
        type: VIEW_MEMORY_TYPE[view] ? [VIEW_MEMORY_TYPE[view] as MemoryType] : undefined,
        invalidated_only: view === 'invalidated',
        limit: 200,
      }),
    enabled: !searching && view !== 'preferences',
  })

  const searchQuery = useQuery({
    queryKey: ['lifeops', 'memory', 'search', trimmedQuery],
    queryFn: () => memoryApi.search(trimmedQuery, { limit: 50 }),
    enabled: searching,
  })

  const preferencesQuery = useQuery({
    queryKey: ['lifeops', 'preferences', 'list'],
    queryFn: () => preferencesApi.list(),
    enabled: view === 'preferences',
  })

  const activeQuery = view === 'preferences' ? preferencesQuery : searching ? searchQuery : listQuery
  const viewType = VIEW_MEMORY_TYPE[view] as MemoryType | undefined
  const memories =
    view === 'preferences'
      ? []
      : ((searching ? searchQuery.data?.memories : listQuery.data?.memories) ?? [])
          // Server search has no type filter, so a typed view (Episodic,
          // Procedures, …) applies its type to the results here — results
          // from other types no longer appear under the active chip.
          .filter((memory) => !searching || !viewType || memory.type === viewType)
          .filter(
            (memory) =>
              view !== 'invalidated' ||
              !trimmedQuery ||
              memory.content.toLowerCase().includes(trimmedQuery.toLowerCase()),
          )
          .filter(
            (memory) => sourceFilter === 'all' || memory.source_type === sourceFilter,
          )
  const preferences =
    view === 'preferences'
      ? (preferencesQuery.data?.preferences ?? []).filter(
          (preference) => sourceFilter === 'all' || preference.source_type === sourceFilter,
        )
      : []

  if (activeQuery.isError) {
    return (
      <div className="p-8">
        <QueryError
          message={errorMessage(activeQuery.error)}
          onRetry={() => void activeQuery.refetch()}
        />
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-8">
      <header>
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <Brain className="h-5 w-5" />
          Memory
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          What the assistant remembers, with full provenance. Memory observes the
          world — it never rewrites tasks, approvals, or payments.
        </p>
      </header>

      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={
              view === 'preferences' ? 'Search is not available for preferences' : 'Search memories…'
            }
            aria-label="Search memories"
            className="pl-8"
            disabled={view === 'preferences'}
          />
          {view === 'invalidated' && trimmedQuery.length > 0 && (
            <p className="mt-1 text-xs text-muted-foreground">
              Filtering the invalidated history locally — server search covers
              current memories only.
            </p>
          )}
        </div>
        <select
          className="rounded-md border border-border bg-background px-2 py-1 text-sm"
          value={sourceFilter}
          onChange={(event) => setSourceFilter(event.target.value)}
          aria-label="Filter by source"
        >
          {SOURCE_FILTERS.map((option) => (
            <option key={option.id} value={option.id}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {VIEWS.map((option) => (
          <button
            key={option.id}
            type="button"
            onClick={() => {
              setView(option.id)
              setSelected(null)
              setSelectedPreference(null)
            }}
            className={cn(
              'rounded-full border px-3 py-1 text-xs transition-colors',
              view === option.id
                ? 'border-foreground bg-foreground text-background'
                : 'border-border text-muted-foreground hover:bg-muted',
            )}
          >
            {option.label}
          </button>
        ))}
        <span className="ml-auto text-xs text-muted-foreground">
          {view === 'invalidated'
            ? 'Closed and superseded records, newest-closed first.'
            : "Closed and superseded versions live in each record's history."}
        </span>
      </div>

      {activeQuery.isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading…
        </div>
      ) : view === 'preferences' ? (
        preferences.length === 0 ? (
          <p className="rounded-lg border border-dashed border-border/60 px-4 py-8 text-center text-sm text-muted-foreground">
            No preferences recorded yet.
          </p>
        ) : (
          <div className="space-y-2">
            {preferences.map((preference) => (
              <PreferenceCard
                key={preference.id}
                preference={preference}
                selected={selectedPreference?.id === preference.id}
                onSelect={() =>
                  setSelectedPreference((current) =>
                    current?.id === preference.id ? null : preference,
                  )
                }
              />
            ))}
          </div>
        )
      ) : memories.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border/60 px-4 py-8 text-center text-sm text-muted-foreground">
          {searching ? 'No memories match that search.' : 'Nothing recorded in this view yet.'}
        </p>
      ) : (
        <div className="space-y-2">
          {memories.map((memory) => (
            <MemoryCard
              key={memory.id}
              memory={memory}
              selected={selected?.id === memory.id}
              onSelect={() =>
                setSelected((current) => (current?.id === memory.id ? null : memory))
              }
            />
          ))}
        </div>
      )}

      {view === 'preferences'
        ? selectedPreference && (
            <PreferenceDetail
              preference={selectedPreference}
              onChanged={setSelectedPreference}
            />
          )
        : selected && <MemoryDetail memory={selected} onChanged={setSelected} />}
    </div>
  )
}
