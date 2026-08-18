/**
 * Routines — workflow templates Hermes may create, revise, and run against
 * itself through an approved interface (BUILD_SPEC sections 73, 100).
 *
 * A template is a named, reusable shape of work with an ordered list of
 * steps, a trigger, and — for scheduled routines — a next run time. LifeOps
 * Core owns every rule here: what counts as a valid trigger, when a
 * scheduled routine is due, how many steps a template may hold before it is
 * really a program that belongs in reviewed code (section 73's boundary).
 * This screen only renders what the server returns and submits what a human
 * asks it to save or delete.
 *
 * Saving is keyed by name — the id is derived from it server-side — so
 * saving an existing name revises that template rather than creating a
 * second one with the same name. This screen surfaces that by opening the
 * same dialog, pre-filled, for "Revise".
 */

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Pencil, Plus, Repeat, Trash2 } from 'lucide-react'

import { QueryError } from '@/components/QueryError'
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
import { cn } from '@/lib/utils'
import {
  LifeOpsError,
  TRIGGER_KIND_LABELS,
  errorMessage,
  workflowTemplatesApi,
  type TriggerKind,
  type WorkflowStep,
  type WorkflowTemplate,
} from '@/services/lifeops'

function formatNextRun(iso: string | null): string {
  if (!iso) return 'not scheduled'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

/** `datetime-local` needs `YYYY-MM-DDTHH:mm`; the server sends full ISO. */
function toLocalInputValue(iso: string | null): string {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

// --- create / revise dialog ---------------------------------------------------

interface DraftStep {
  description: string
  action_type: string
}

function SaveTemplateDialog({
  template,
  onClose,
}: {
  /** `'new'` opens a blank form; a template opens pre-filled for revision;
   * `null` keeps the dialog closed. */
  template: WorkflowTemplate | 'new' | null
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const editing = template !== null && template !== 'new' ? template : null

  const [name, setName] = useState(editing?.name ?? '')
  const [description, setDescription] = useState(editing?.description ?? '')
  const [trigger, setTrigger] = useState<TriggerKind>(editing?.trigger ?? 'manual')
  const [nextRunAt, setNextRunAt] = useState(toLocalInputValue(editing?.next_run_at ?? null))
  // A new routine starts enabled; revising one keeps whatever it was.
  const [enabled, setEnabled] = useState(editing?.enabled ?? true)
  const [steps, setSteps] = useState<DraftStep[]>(
    editing?.steps.map((s) => ({ description: s.description, action_type: s.action_type ?? '' })) ?? [],
  )
  const [error, setError] = useState<string | null>(null)

  // Re-seed the form whenever a different template opens for revision, or
  // "new" opens a blank one — a stable `key` on the dialog (below) makes each
  // open a fresh mount, which is simpler than syncing state across props.

  const save = useMutation({
    mutationFn: () =>
      workflowTemplatesApi.save({
        name: name.trim(),
        description: description.trim() || undefined,
        steps: steps
          .filter((s) => s.description.trim() !== '')
          .map((s, index): WorkflowStep => ({
            order: index,
            description: s.description.trim(),
            action_type: s.action_type.trim() || null,
          })),
        trigger,
        // The input holds a *local* wall time; new Date() parses it as such
        // and toISOString() converts to real UTC. Appending "Z" to the raw
        // value stamped local time as UTC and shifted every save by the
        // user's offset.
        next_run_at:
          trigger === 'schedule' && nextRunAt
            ? new Date(nextRunAt).toISOString()
            : undefined,
        // Carried explicitly: the server rebuilds the template from this
        // payload, so omitting it would switch a paused routine back on.
        enabled,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'workflow-templates'] })
      onClose()
    },
    onError: (err) => {
      setError(err instanceof LifeOpsError ? err.message : 'Could not save the routine.')
    },
  })

  const updateStep = (index: number, patch: Partial<DraftStep>) => {
    setSteps((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)))
  }

  const valid = name.trim() !== '' && (trigger !== 'schedule' || nextRunAt !== '')

  return (
    <Dialog
      open={template !== null}
      onOpenChange={(next) => {
        if (!next) onClose()
      }}
    >
      <DialogContent className="max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{editing ? `Revise ${editing.name}` : 'New routine'}</DialogTitle>
          <DialogDescription>
            {editing
              ? 'Saving keeps the same name, so this revises the existing routine rather than creating a second one.'
              : 'A named, reusable shape of work. Hermes may run and revise routine templates through this same interface.'}
          </DialogDescription>
        </DialogHeader>

        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            if (valid) save.mutate()
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="routine-name">Name</Label>
            <Input
              id="routine-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Weekly review"
              disabled={save.isPending || editing !== null}
            />
            {editing && (
              <p className="text-xs text-muted-foreground">
                The name is fixed once a routine exists — it is how LifeOps
                tells this revision apart from a new routine.
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="routine-description">Description (optional)</Label>
            <Input
              id="routine-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="What this routine is for"
              disabled={save.isPending}
            />
          </div>

          <div className="flex gap-3">
            <div className="flex-1 space-y-1.5">
              <Label htmlFor="routine-trigger">Trigger</Label>
              <select
                id="routine-trigger"
                className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm"
                value={trigger}
                onChange={(event) => setTrigger(event.target.value as TriggerKind)}
                disabled={save.isPending}
              >
                {(Object.keys(TRIGGER_KIND_LABELS) as TriggerKind[]).map((kind) => (
                  <option key={kind} value={kind}>
                    {TRIGGER_KIND_LABELS[kind]}
                  </option>
                ))}
              </select>
            </div>
            {trigger === 'schedule' && (
              <div className="flex-1 space-y-1.5">
                <Label htmlFor="routine-next-run">Next run</Label>
                <Input
                  id="routine-next-run"
                  type="datetime-local"
                  value={nextRunAt}
                  onChange={(event) => setNextRunAt(event.target.value)}
                  disabled={save.isPending}
                />
              </div>
            )}
          </div>
          {trigger === 'schedule' && !nextRunAt && (
            <p className="text-xs text-amber-600">
              A scheduled routine needs a next run time, or it will never run.
            </p>
          )}

          <div className="space-y-1.5">
            <Label>Steps</Label>
            {steps.map((step, index) => (
              <div key={index} className="flex items-center gap-2">
                <span className="w-5 shrink-0 text-right text-xs text-muted-foreground">
                  {index + 1}
                </span>
                <Input
                  value={step.description}
                  onChange={(event) => updateStep(index, { description: event.target.value })}
                  placeholder="Step description"
                  aria-label={`Step ${index + 1} description`}
                  disabled={save.isPending}
                />
                <Input
                  value={step.action_type}
                  onChange={(event) => updateStep(index, { action_type: event.target.value })}
                  placeholder="action type (optional)"
                  aria-label={`Step ${index + 1} action type`}
                  className="w-40"
                  disabled={save.isPending}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  aria-label={`Remove step ${index + 1}`}
                  onClick={() => setSteps((rows) => rows.filter((_, i) => i !== index))}
                  disabled={save.isPending}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            ))}
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setSteps((rows) => [...rows, { description: '', action_type: '' }])}
              disabled={save.isPending}
            >
              <Plus className="mr-1 h-3 w-3" />
              Add step
            </Button>
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(event) => setEnabled(event.target.checked)}
              disabled={save.isPending}
              className="h-4 w-4"
            />
            <span>Enabled</span>
            <span className="text-xs text-muted-foreground">
              A paused routine keeps its schedule but never runs.
            </span>
          </label>

          {error && (
            <p className="rounded border border-red-300 bg-red-50 px-2 py-1 text-xs text-red-700">
              {error}
            </p>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={save.isPending}>
              Cancel
            </Button>
            <Button type="submit" disabled={!valid || save.isPending}>
              {save.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : editing ? (
                'Save revision'
              ) : (
                'Create'
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

// --- rows -----------------------------------------------------------------------

function TemplateCard({
  template,
  onRevise,
  onDelete,
  deleting,
}: {
  template: WorkflowTemplate
  onRevise: () => void
  onDelete: () => void
  deleting: boolean
}) {
  return (
    <div className="rounded-lg border border-border/60 bg-card p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="flex items-center gap-2 font-medium">
            {template.name}
            <span
              className={cn(
                'rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide',
                template.enabled
                  ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-400'
                  : 'bg-muted text-muted-foreground',
              )}
            >
              {template.enabled ? 'Enabled' : 'Disabled'}
            </span>
          </p>
          {template.description && (
            <p className="mt-1 text-sm text-muted-foreground">{template.description}</p>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span>{TRIGGER_KIND_LABELS[template.trigger]}</span>
            {template.trigger === 'schedule' && (
              <span>next run {formatNextRun(template.next_run_at)}</span>
            )}
            <span>
              {template.steps.length} {template.steps.length === 1 ? 'step' : 'steps'}
            </span>
          </div>
        </div>

        <div className="flex shrink-0 gap-1.5">
          <Button variant="outline" size="sm" onClick={onRevise}>
            <Pencil className="mr-1 h-3.5 w-3.5" />
            Revise
          </Button>
          <Button
            variant="ghost"
            size="sm"
            aria-label={`Delete ${template.name}`}
            disabled={deleting}
            onClick={onDelete}
          >
            {deleting ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Trash2 className="h-3.5 w-3.5" />
            )}
          </Button>
        </div>
      </div>

      {template.steps.length > 0 && (
        <ol className="mt-3 space-y-1 border-t border-border/60 pt-3 text-sm">
          {template.steps.map((step) => (
            <li key={step.order} className="flex items-baseline gap-2">
              <span className="text-xs text-muted-foreground">{step.order + 1}.</span>
              <span>{step.description}</span>
              {step.action_type && (
                <span className="text-xs text-muted-foreground">({step.action_type})</span>
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

// --- page -----------------------------------------------------------------------

export function RoutinesPage() {
  const queryClient = useQueryClient()
  const [dialogTemplate, setDialogTemplate] = useState<WorkflowTemplate | 'new' | null>(null)

  const templatesQuery = useQuery({
    queryKey: ['lifeops', 'workflow-templates'],
    queryFn: () => workflowTemplatesApi.list({ limit: 200 }),
  })

  const remove = useMutation({
    mutationFn: (id: string) => workflowTemplatesApi.delete(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'workflow-templates'] })
    },
  })

  if (templatesQuery.isError) {
    return (
      <div className="p-8">
        <QueryError
          message={errorMessage(templatesQuery.error)}
          onRetry={() => void templatesQuery.refetch()}
        />
      </div>
    )
  }

  const templates = templatesQuery.data?.templates ?? []

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <Repeat className="h-5 w-5" />
            Routines
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Named, reusable shapes of work. A permitted self-change — Hermes
            may create and revise these through the same interface as you.
          </p>
        </div>
        <Button onClick={() => setDialogTemplate('new')}>
          <Plus className="mr-1 h-4 w-4" />
          New routine
        </Button>
      </header>

      {templatesQuery.isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading…
        </div>
      ) : templates.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border/60 px-4 py-8 text-center text-sm text-muted-foreground">
          No routines yet.
        </p>
      ) : (
        <div className="space-y-3">
          {templates.map((template) => (
            <TemplateCard
              key={template.id}
              template={template}
              onRevise={() => setDialogTemplate(template)}
              onDelete={() => remove.mutate(template.id)}
              deleting={remove.isPending && remove.variables === template.id}
            />
          ))}
        </div>
      )}

      <SaveTemplateDialog
        key={dialogTemplate === null ? 'closed' : dialogTemplate === 'new' ? 'new' : dialogTemplate.id}
        template={dialogTemplate}
        onClose={() => setDialogTemplate(null)}
      />
    </div>
  )
}
