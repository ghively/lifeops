/**
 * Link-entities dialog (BUILD_SPEC section 15). Linking is a domain operation
 * with a typed relationship between two known entities — never free-form edge
 * editing on the canvas.
 */

import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import {
  LifeOpsError,
  WORLD_RELATIONSHIP_TYPES,
  worldApi,
  worldTypeLabel,
  type WorldGraphNode,
} from '@/services/lifeops'

/**
 * How each relationship reads left-to-right, so the form describes the edge
 * it is actually about to create rather than leaving the user to guess the
 * direction from a constant name. Keyed over the whole BUILD_SPEC section 39
 * vocabulary; a type with no hint still renders under its own name.
 */
const TYPE_HINTS: Record<string, string> = {
  MEMBER_OF: 'is a member of',
  RELATED_TO: 'is related to',
  PREFERS: 'prefers',
  OWNS: 'owns',
  USES_PROVIDER: 'uses as a provider',
  ASSIGNED_TO: 'is assigned to',
  ABOUT: 'is about',
  WITH_PROVIDER: 'is handled by',
  FOR_ASSET: 'concerns the asset',
  WAITING_ON: 'is waiting on',
  REQUIRES_APPROVAL: 'requires approval from',
  AUTHORIZES: 'authorizes',
  CREATED_BY: 'was created by',
  REQUESTED_BY: 'was requested by',
  EXECUTED_BY: 'was executed by',
  VERIFIED_BY: 'was verified by',
  DERIVED_FROM: 'is derived from',
  SUPERSEDES: 'supersedes',
  RELATED_MEMORY: 'relates to the memory',
  REFERENCES: 'references',
}

export function LinkEntitiesDialog({
  open,
  nodes,
  initialSourceId,
  onClose,
  onLinked,
}: {
  open: boolean
  nodes: WorldGraphNode[]
  initialSourceId?: string | null
  onClose: () => void
  onLinked: () => void
}) {
  const queryClient = useQueryClient()
  const [sourceId, setSourceId] = useState('')
  const [targetId, setTargetId] = useState('')
  const [type, setType] = useState('')
  const [actionError, setActionError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setSourceId(initialSourceId ?? '')
      setTargetId('')
      setType('')
      setActionError(null)
    }
  }, [open, initialSourceId])

  const sortedNodes = [...nodes].sort((a, b) => a.label.localeCompare(b.label))

  const link = useMutation({
    mutationFn: () =>
      worldApi.link({ source_id: sourceId, target_id: targetId, rel_type: type }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'world'] })
      onLinked()
    },
    onError: (error) => {
      setActionError(
        error instanceof LifeOpsError ? error.message : 'Could not create the link.',
      )
    },
  })

  const valid =
    sourceId !== '' && targetId !== '' && sourceId !== targetId && type !== ''

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose()
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Link two entities</DialogTitle>
          <DialogDescription>
            Record a typed relationship, like a person MEMBER_OF a household
            or a household USES_PROVIDER an electrician.
          </DialogDescription>
        </DialogHeader>

        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            if (valid) link.mutate()
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="world-link-source">From</Label>
            <select
              id="world-link-source"
              className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm"
              value={sourceId}
              onChange={(event) => setSourceId(event.target.value)}
              disabled={link.isPending}
            >
              <option value="">Choose an entity…</option>
              {sortedNodes.map((node) => (
                <option key={node.id} value={node.id}>
                  {node.label} ({worldTypeLabel(node.entity_type)})
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="world-link-type">Relationship type</Label>
            <select
              id="world-link-type"
              className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm"
              value={type}
              onChange={(event) => setType(event.target.value)}
              disabled={link.isPending}
            >
              <option value="">Choose a relationship…</option>
              {WORLD_RELATIONSHIP_TYPES.map((option) => (
                <option key={option} value={option}>
                  {TYPE_HINTS[option] ? `${option} — ${TYPE_HINTS[option]}` : option}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="world-link-target">To</Label>
            <select
              id="world-link-target"
              className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm"
              value={targetId}
              onChange={(event) => setTargetId(event.target.value)}
              disabled={link.isPending}
            >
              <option value="">Choose an entity…</option>
              {sortedNodes.map((node) => (
                <option key={node.id} value={node.id}>
                  {node.label} ({worldTypeLabel(node.entity_type)})
                </option>
              ))}
            </select>
          </div>

          {sourceId !== '' && sourceId === targetId && (
            <p className="text-xs text-muted-foreground">
              An entity cannot be linked to itself.
            </p>
          )}

          {actionError && (
            <p className="rounded border border-red-300 bg-red-50 px-2 py-1 text-xs text-red-700">
              {actionError}
            </p>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={link.isPending}>
              Cancel
            </Button>
            <Button type="submit" disabled={!valid || link.isPending}>
              {link.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Link'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
