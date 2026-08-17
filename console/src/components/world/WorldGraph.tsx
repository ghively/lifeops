/**
 * The interactive world graph (BUILD_SPEC section 15).
 *
 * A thin React Flow wrapper: the page owns the data (base graph plus clicked
 * expansions); this component turns it into positioned, coloured nodes and
 * labelled edges and wires zoom/pan/fit, which React Flow provides. Layout is
 * deliberately simple and deterministic — the base graph sits on a circle and
 * expanded neighbours on a ring around the node that revealed them — because
 * section 15 asks for inspection, not cartography.
 */

import { useEffect, useMemo } from 'react'
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import { cn } from '@/lib/utils'
import type { WorldGraph } from '@/services/lifeops'

/** Node colour per entity type; unknown types fall back to slate. */
const TYPE_COLORS: Record<string, string> = {
  person: '#2563eb',
  household: '#7c3aed',
  provider: '#d97706',
  asset: '#059669',
  task: '#dc2626',
  waiting_item: '#ea580c',
  appointment: '#0891b2',
  event: '#0891b2',
  preference: '#0d9488',
  memory: '#64748b',
  knowledge: '#4b5563',
  document: '#4b5563',
}

const FALLBACK_COLOR = '#475569'

export function entityTypeColor(entityType: string): string {
  return TYPE_COLORS[entityType] ?? FALLBACK_COLOR
}

type LifeOpsNodeData = {
  label: string
  entityType: string
  status: string | null
  highlighted: boolean
  selected: boolean
}

type LifeOpsFlowNode = Node<LifeOpsNodeData, 'lifeops'>

function LifeOpsGraphNode({ data }: NodeProps<LifeOpsFlowNode>) {
  const color = entityTypeColor(data.entityType)
  return (
    <div
      className={cn(
        'rounded-md border-2 bg-card px-3 py-1.5 text-xs shadow-sm',
        data.highlighted && 'ring-2 ring-offset-2',
        data.selected && 'shadow-md',
      )}
      style={{
        borderColor: color,
        boxShadow: data.selected ? `0 0 0 2px ${color}` : undefined,
      }}
    >
      <Handle type="target" position={Position.Top} />
      <span className="flex items-center gap-1.5">
        <span
          className="inline-block h-2 w-2 rounded-full"
          style={{ backgroundColor: color }}
        />
        <span className="font-medium">{data.label}</span>
      </span>
      {data.status && (
        <span className="mt-0.5 block text-[10px] text-muted-foreground">{data.status}</span>
      )}
      <Handle type="source" position={Position.Bottom} />
    </div>
  )
}

const nodeTypes = { lifeops: LifeOpsGraphNode }

/**
 * Deterministic positions: base-graph nodes on a circle, each expansion's new
 * nodes on a ring around the node that was clicked to reveal them.
 */
export function computeWorldLayout(
  graph: WorldGraph,
  expansionChildren: Record<string, string[]>,
): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>()
  const expandedIds = new Set(Object.values(expansionChildren).flat())

  const baseNodes = graph.nodes
    .filter((node) => !expandedIds.has(node.id))
    .sort((a, b) => a.id.localeCompare(b.id))
  const radius = Math.max(220, baseNodes.length * 42)
  baseNodes.forEach((node, index) => {
    const angle = (2 * Math.PI * index) / Math.max(baseNodes.length, 1) - Math.PI / 2
    positions.set(node.id, {
      x: Math.round(radius * Math.cos(angle)),
      y: Math.round(radius * Math.sin(angle)),
    })
  })

  for (const [expanderId, childIds] of Object.entries(expansionChildren)) {
    const center = positions.get(expanderId) ?? { x: 0, y: 0 }
    const children = graph.nodes
      .filter((node) => childIds.includes(node.id) && !positions.has(node.id))
      .sort((a, b) => a.id.localeCompare(b.id))
    children.forEach((node, index) => {
      // Golden-angle spread keeps rings from overlapping as they grow.
      const angle = index * 2.399963 - Math.PI / 2
      positions.set(node.id, {
        x: Math.round(center.x + 190 * Math.cos(angle)),
        y: Math.round(center.y + 190 * Math.sin(angle)),
      })
    })
  }

  return positions
}

export interface WorldGraphViewProps {
  graph: WorldGraph
  /** Node ids each expansion introduced, keyed by the node that was expanded. */
  expansionChildren: Record<string, string[]>
  selectedId: string | null
  highlightedId: string | null
  /** 'all' shows every relationship; anything else shows only that type. */
  visibleEdgeType: string
  /** Center the view on this node; `nonce` re-triggers for the same id. */
  focusRequest: { id: string; nonce: number } | null
  onNodeClick: (id: string) => void
}

function FocusHandler({
  focusRequest,
  positions,
}: {
  focusRequest: { id: string; nonce: number } | null
  positions: Map<string, { x: number; y: number }>
}) {
  const { setCenter } = useReactFlow()
  useEffect(() => {
    if (!focusRequest) return
    const position = positions.get(focusRequest.id)
    if (position) {
      // +90/+24 aims at the node's middle rather than its top-left corner.
      void setCenter(position.x + 90, position.y + 24, { zoom: 1.3, duration: 400 })
    }
  }, [focusRequest, positions, setCenter])
  return null
}

function WorldGraphInner({
  graph,
  expansionChildren,
  selectedId,
  highlightedId,
  visibleEdgeType,
  focusRequest,
  onNodeClick,
}: WorldGraphViewProps) {
  const positions = useMemo(
    () => computeWorldLayout(graph, expansionChildren),
    [graph, expansionChildren],
  )

  const nodes = useMemo<LifeOpsFlowNode[]>(
    () =>
      graph.nodes.map((node) => ({
        id: node.id,
        type: 'lifeops',
        position: positions.get(node.id) ?? { x: 0, y: 0 },
        data: {
          label: node.label,
          entityType: node.entity_type,
          status: node.status,
          highlighted: node.id === highlightedId,
          selected: node.id === selectedId,
        },
      })),
    [graph, positions, highlightedId, selectedId],
  )

  const edges = useMemo<Edge[]>(() => {
    const nodeIds = new Set(graph.nodes.map((node) => node.id))
    return graph.edges
      .filter((edge) => visibleEdgeType === 'all' || edge.type === visibleEdgeType)
      .filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target))
      .map((edge) => ({
        id: `${edge.source}|${edge.type}|${edge.target}`,
        source: edge.source,
        target: edge.target,
        label: edge.type,
        markerEnd: { type: MarkerType.ArrowClosed },
        labelStyle: { fontSize: 10 },
        className: 'world-graph-edge',
      }))
  }, [graph, visibleEdgeType])

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      onNodeClick={(_, node) => onNodeClick(node.id)}
      fitView
      minZoom={0.15}
      nodesConnectable={false}
    >
      <Background />
      <Controls />
      <FocusHandler focusRequest={focusRequest} positions={positions} />
    </ReactFlow>
  )
}

export function WorldGraphView(props: WorldGraphViewProps) {
  return (
    <ReactFlowProvider>
      <WorldGraphInner {...props} />
    </ReactFlowProvider>
  )
}
