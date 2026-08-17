/**
 * Create-entity dialog (BUILD_SPEC section 15). The graph offers no raw
 * editing; the only way a household, provider, or asset enters the world from
 * this screen is this domain operation. Facts are optional initial key/value
 * pairs — the server validates them and refuses anything secret-shaped.
 */

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Loader2, Plus, Trash2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  LifeOpsError,
  worldApi,
  type WorldCreatableType,
  type WorldEntity,
} from '@/services/lifeops'

const TYPE_OPTIONS: Array<{ id: WorldCreatableType; label: string }> = [
  { id: 'household', label: 'Household' },
  { id: 'provider', label: 'Provider' },
  { id: 'asset', label: 'Asset' },
]

interface FactRow {
  key: string
  value: string
}

export function CreateEntityDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean
  onClose: () => void
  onCreated: (entity: WorldEntity) => void
}) {
  const queryClient = useQueryClient()
  const [entityType, setEntityType] = useState<WorldCreatableType>('household')
  const [displayName, setDisplayName] = useState('')
  const [factRows, setFactRows] = useState<FactRow[]>([])
  const [actionError, setActionError] = useState<string | null>(null)

  const reset = () => {
    setEntityType('household')
    setDisplayName('')
    setFactRows([])
    setActionError(null)
  }

  const create = useMutation({
    mutationFn: () => {
      const facts = Object.fromEntries(
        factRows
          .filter((row) => row.key.trim() !== '')
          .map((row) => [row.key.trim(), row.value.trim()]),
      )
      return worldApi.createEntity({
        entity_type: entityType,
        display_name: displayName.trim(),
        facts: Object.keys(facts).length > 0 ? facts : undefined,
      })
    },
    onSuccess: (entity) => {
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'world'] })
      reset()
      onCreated(entity)
    },
    onError: (error) => {
      setActionError(
        error instanceof LifeOpsError ? error.message : 'Could not create the entity.',
      )
    },
  })

  const updateRow = (index: number, patch: Partial<FactRow>) => {
    setFactRows((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)))
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          reset()
          onClose()
        }
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add to the world</DialogTitle>
          <DialogDescription>
            Create a household, provider, or asset. People arrive through Hermes
            and setup, not through this form.
          </DialogDescription>
        </DialogHeader>

        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            if (displayName.trim()) create.mutate()
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="world-entity-type">Type</Label>
            <select
              id="world-entity-type"
              className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm"
              value={entityType}
              onChange={(event) => setEntityType(event.target.value as WorldCreatableType)}
              disabled={create.isPending}
            >
              {TYPE_OPTIONS.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="world-entity-name">Name</Label>
            <Input
              id="world-entity-name"
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              placeholder="ABC Electric"
              disabled={create.isPending}
            />
          </div>

          <div className="space-y-1.5">
            <Label>Facts (optional)</Label>
            {factRows.map((row, index) => (
              <div key={index} className="flex items-center gap-2">
                <Input
                  value={row.key}
                  onChange={(event) => updateRow(index, { key: event.target.value })}
                  placeholder="key"
                  aria-label={`Fact ${index + 1} key`}
                  className="w-2/5"
                  disabled={create.isPending}
                />
                <Input
                  value={row.value}
                  onChange={(event) => updateRow(index, { value: event.target.value })}
                  placeholder="value"
                  aria-label={`Fact ${index + 1} value`}
                  disabled={create.isPending}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  aria-label={`Remove fact ${index + 1}`}
                  onClick={() => setFactRows((rows) => rows.filter((_, i) => i !== index))}
                  disabled={create.isPending}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            ))}
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setFactRows((rows) => [...rows, { key: '', value: '' }])}
              disabled={create.isPending}
            >
              <Plus className="mr-1 h-3 w-3" />
              Add fact
            </Button>
          </div>

          {actionError && (
            <p className="rounded border border-red-300 bg-red-50 px-2 py-1 text-xs text-red-700">
              {actionError}
            </p>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={create.isPending}>
              Cancel
            </Button>
            <Button type="submit" disabled={!displayName.trim() || create.isPending}>
              {create.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Create'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
