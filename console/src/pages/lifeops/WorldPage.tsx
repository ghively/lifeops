/**
 * World — the interactive graph of the LifeOps world model (BUILD_SPEC
 * sections 15 and 92).
 *
 * The base graph comes from GET /world/graph; clicking a node selects it for
 * the inspector and expands its neighborhood, clicking it again collapses the
 * branch it revealed. Filters are honest about where they run: entity-type
 * filters go to the API (the server narrows the graph), the relationship-type
 * filter hides edges client-side because the graph contract has no such
 * parameter.
 *
 * There is deliberately no raw editing here (section 15): creation and
 * linking happen through the two domain-operation dialogs, and corrections
 * go through LifeOps operations.
 */

import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Globe, Link2, Loader2, Plus, Search } from 'lucide-react'

import { QueryError } from '@/components/QueryError'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { CreateEntityDialog } from '@/components/world/CreateEntityDialog'
import { EntityInspector } from '@/components/world/EntityInspector'
import { LinkEntitiesDialog } from '@/components/world/LinkEntitiesDialog'
import { WorldGraphView } from '@/components/world/WorldGraph'
import { cn } from '@/lib/utils'
import {
  errorMessage,
  worldApi,
  worldTypeLabel,
  type WorldGraph,
  type WorldGraphEdge,
  type WorldGraphNode,
} from '@/services/lifeops'

const GRAPH_LIMIT = 500

function edgeKey(edge: WorldGraphEdge): string {
  return `${edge.source}|${edge.type}|${edge.target}`
}

/** Merge the base graph with every expansion, deduplicating by id/edge key. */
function mergeGraph(base: WorldGraph | undefined, expansions: Record<string, WorldGraph>): WorldGraph {
  const nodes = new Map<string, WorldGraphNode>()
  const edges = new Map<string, WorldGraphEdge>()
  for (const node of base?.nodes ?? []) nodes.set(node.id, node)
  for (const edge of base?.edges ?? []) edges.set(edgeKey(edge), edge)
  for (const expansion of Object.values(expansions)) {
    for (const node of expansion.nodes) nodes.set(node.id, node)
    for (const edge of expansion.edges) edges.set(edgeKey(edge), edge)
  }
  return { nodes: [...nodes.values()], edges: [...edges.values()] }
}

export function WorldPage() {
  const queryClient = useQueryClient()
  const [typeFilter, setTypeFilter] = useState<string[]>([])
  const [edgeTypeFilter, setEdgeTypeFilter] = useState('all')
  const [search, setSearch] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [highlightedId, setHighlightedId] = useState<string | null>(null)
  const [focusRequest, setFocusRequest] = useState<{ id: string; nonce: number } | null>(null)
  const [expansions, setExpansions] = useState<Record<string, WorldGraph>>({})
  const [dialog, setDialog] = useState<'none' | 'create' | 'link'>('none')

  const graphQuery = useQuery({
    queryKey: ['lifeops', 'world', 'graph', typeFilter],
    queryFn: () =>
      worldApi.graph({ types: typeFilter.length > 0 ? typeFilter : undefined, limit: GRAPH_LIMIT }),
  })

  const expand = useMutation({
    mutationFn: (entityId: string) => worldApi.neighborhood(entityId, 1),
    onSuccess: (graph, entityId) => {
      setExpansions((current) => ({ ...current, [entityId]: graph }))
    },
  })

  const base = graphQuery.data
  const graph = useMemo(() => mergeGraph(base, expansions), [base, expansions])

  /** Node ids each expansion introduced, for the ring layout and collapse. */
  const expansionChildren = useMemo(() => {
    const baseIds = new Set((base?.nodes ?? []).map((node) => node.id))
    const children: Record<string, string[]> = {}
    for (const [expanderId, expansion] of Object.entries(expansions)) {
      children[expanderId] = expansion.nodes
        .map((node) => node.id)
        .filter((id) => id !== expanderId && !baseIds.has(id))
    }
    return children
  }, [base, expansions])

  const presentTypes = useMemo(
    () => [...new Set(graph.nodes.map((node) => node.entity_type))].sort(),
    [graph],
  )
  const presentEdgeTypes = useMemo(
    () => [...new Set(graph.edges.map((edge) => edge.type))].sort(),
    [graph],
  )

  const searchMatches = useMemo(() => {
    const query = search.trim().toLowerCase()
    if (!query) return []
    return graph.nodes
      .filter((node) => node.label.toLowerCase().includes(query))
      .sort((a, b) => a.label.localeCompare(b.label))
      .slice(0, 8)
  }, [graph, search])

  /** A world holding only the primary person is an honest empty state. */
  const worldIsOnlyYou = (base?.nodes.length ?? 0) <= 1 && Object.keys(expansions).length === 0

  const selectEntity = (id: string) => {
    setSelectedId(id)
    setHighlightedId(null)
  }

  const handleNodeClick = (id: string) => {
    if (selectedId === id && expansions[id]) {
      // Second click on an expanded node collapses the branch it revealed.
      setExpansions((current) => {
        const next = { ...current }
        delete next[id]
        return next
      })
      return
    }
    selectEntity(id)
    if (!expansions[id] && !expand.isPending) {
      expand.mutate(id)
    }
  }

  const goToNode = (id: string) => {
    selectEntity(id)
    setHighlightedId(id)
    setFocusRequest({ id, nonce: Date.now() })
    setSearch('')
  }

  /** After a create/link/unlink the server graph is authoritative again.
   *
   * Expansions are dropped *and* the base query refetched: keeping a stale
   * base would hide the entity that was just created. */
  const resetGraphState = () => {
    setExpansions({})
    void queryClient.invalidateQueries({ queryKey: ['lifeops', 'world'] })
  }

  const toggleType = (type: string) => {
    // A new base graph makes every recorded expansion stale.
    setExpansions({})
    setTypeFilter((current) =>
      current.includes(type) ? current.filter((t) => t !== type) : [...current, type],
    )
  }

  if (graphQuery.isError) {
    return (
      <div className="p-8">
        <QueryError
          message={errorMessage(graphQuery.error)}
          onRetry={() => void graphQuery.refetch()}
        />
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <header className="flex flex-wrap items-center gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <Globe className="h-5 w-5" />
            World
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            People, household, providers, and assets as Hermes knows them. Click a
            node to inspect it and expand its neighborhood; click again to
            collapse the branch.
          </p>
        </div>
        <div className="ml-auto flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setDialog('create')}>
            <Plus className="mr-1 h-4 w-4" />
            Add entity
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setDialog('link')}
            disabled={graph.nodes.length < 2}
          >
            <Link2 className="mr-1 h-4 w-4" />
            Link entities
          </Button>
        </div>
      </header>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && searchMatches.length > 0) {
                goToNode(searchMatches[0].id)
              }
            }}
            placeholder="Find an entity…"
            aria-label="Find an entity"
            className="w-64 pl-8"
          />
          {searchMatches.length > 0 && (
            <ul className="absolute z-10 mt-1 w-64 rounded-md border border-border bg-background py-1 shadow-md">
              {searchMatches.map((node) => (
                <li key={node.id}>
                  <button
                    type="button"
                    className="flex w-full items-center justify-between px-3 py-1.5 text-left text-sm hover:bg-muted"
                    onClick={() => goToNode(node.id)}
                  >
                    <span className="truncate">{node.label}</span>
                    <span className="ml-2 text-xs text-muted-foreground">
                      {worldTypeLabel(node.entity_type)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-1.5" aria-label="Entity type filters">
          {presentTypes.map((type) => (
            <button
              key={type}
              type="button"
              aria-pressed={typeFilter.includes(type)}
              onClick={() => toggleType(type)}
              className={cn(
                'rounded-full border px-3 py-1 text-xs transition-colors',
                typeFilter.includes(type)
                  ? 'border-foreground bg-foreground text-background'
                  : 'border-border text-muted-foreground hover:bg-muted',
              )}
            >
              {worldTypeLabel(type)}
            </button>
          ))}
        </div>

        <select
          className="ml-auto rounded-md border border-border bg-background px-2 py-1 text-sm"
          value={edgeTypeFilter}
          onChange={(event) => setEdgeTypeFilter(event.target.value)}
          aria-label="Filter relationships"
        >
          <option value="all">All relationships</option>
          {presentEdgeTypes.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
      </div>

      <div className="flex min-h-0 flex-1 gap-4">
        <div className="relative min-h-[480px] flex-1 rounded-lg border border-border/60 bg-card">
          {graphQuery.isLoading ? (
            <div className="flex h-full items-center justify-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading the world…
            </div>
          ) : (
            <>
              {expand.isError ? (
                <p
                  role="alert"
                  className="absolute inset-x-8 top-2 z-10 rounded-md border border-red-300/60 bg-red-50 px-3 py-2 text-center text-xs text-red-700 dark:border-red-800/60 dark:bg-red-950/40 dark:text-red-300"
                >
                  Could not expand that entity: {errorMessage(expand.error)}
                </p>
              ) : null}
              <WorldGraphView
                graph={graph}
                expansionChildren={expansionChildren}
                selectedId={selectedId}
                highlightedId={highlightedId}
                visibleEdgeType={edgeTypeFilter}
                focusRequest={focusRequest}
                onNodeClick={handleNodeClick}
              />
              {worldIsOnlyYou && (
                <p className="pointer-events-none absolute inset-x-8 top-6 rounded-md border border-dashed border-border/60 bg-background/80 px-4 py-3 text-center text-sm text-muted-foreground">
                  {base?.nodes.length === 1
                    ? `Right now your world is just ${base.nodes[0].label}. Providers, assets, and household members appear here as Hermes learns about them — or add them yourself.`
                    : 'Nothing in the world yet. Entities appear here as Hermes learns about them — or add them yourself.'}
                </p>
              )}
            </>
          )}
        </div>

        {selectedId && (
          <EntityInspector
            entityId={selectedId}
            onClose={() => setSelectedId(null)}
            onNavigate={(id) => goToNode(id)}
            onGraphChanged={resetGraphState}
          />
        )}
      </div>

      <CreateEntityDialog
        open={dialog === 'create'}
        onClose={() => setDialog('none')}
        onCreated={(entity) => {
          setDialog('none')
          resetGraphState()
          selectEntity(entity.id)
        }}
      />
      <LinkEntitiesDialog
        open={dialog === 'link'}
        nodes={graph.nodes}
        initialSourceId={selectedId}
        onClose={() => setDialog('none')}
        onLinked={() => {
          setDialog('none')
          resetGraphState()
        }}
      />
    </div>
  )
}
