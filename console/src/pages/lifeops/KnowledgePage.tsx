/**
 * Knowledge — reference content the user authored or distilled (BUILD_SPEC
 * sections 18, 36, 50).
 *
 * Distinct from Memory (what LifeOps has learned or been told) and from
 * Documents/Files (a pointer to something ingested from elsewhere): Knowledge
 * is a note, checklist, or procedure someone wrote — an insurance policy
 * summary, a filter size, a warranty term. Recording it is Console/HTTP-only
 * (the same boundary `create_document` draws, section 18); Hermes can read
 * and search it over MCP (`search_knowledge`) but the write stays a human
 * act.
 *
 * Search matches title, category, and body text (section 50) — a
 * case-insensitive substring match, not yet semantic retrieval.
 */

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BookOpen, Loader2, Plus, Search } from 'lucide-react'

import { QueryError } from '@/components/QueryError'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import {
  LifeOpsError,
  errorMessage,
  knowledgeApi,
  type Knowledge,
} from '@/services/lifeops'

function formatDate(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function KnowledgeCard({ item }: { item: Knowledge }) {
  return (
    <div className="rounded-lg border border-border/60 bg-card px-4 py-3">
      <div className="flex items-start justify-between gap-4">
        <p className="font-medium">{item.title}</p>
        {item.category && (
          <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
            {item.category}
          </span>
        )}
      </div>
      {item.content && <p className="mt-1.5 whitespace-pre-wrap text-sm text-muted-foreground">{item.content}</p>}
      <p className="mt-2 text-xs text-muted-foreground">Recorded {formatDate(item.created_at)}</p>
    </div>
  )
}

export function KnowledgePage() {
  const queryClient = useQueryClient()
  const [query, setQuery] = useState('')
  const [addOpen, setAddOpen] = useState(false)
  const [title, setTitle] = useState('')
  const [category, setCategory] = useState('')
  const [content, setContent] = useState('')

  const knowledgeQuery = useQuery({
    queryKey: ['lifeops', 'knowledge', query],
    queryFn: () => knowledgeApi.search({ q: query, limit: 200 }),
  })

  const create = useMutation({
    mutationFn: () =>
      knowledgeApi.create({
        title: title.trim(),
        category: category.trim() || undefined,
        content: content.trim() || undefined,
      }),
    onSuccess: () => {
      setAddOpen(false)
      setTitle('')
      setCategory('')
      setContent('')
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'knowledge'] })
    },
  })

  if (knowledgeQuery.isError) {
    return (
      <div className="p-8">
        <QueryError
          message={errorMessage(knowledgeQuery.error)}
          onRetry={() => void knowledgeQuery.refetch()}
        />
      </div>
    )
  }

  const items = knowledgeQuery.data?.knowledge ?? []

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-8">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <BookOpen className="h-5 w-5" />
            Knowledge
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Reference notes, checklists, and procedures — kept distinct from
            memory and from documents.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => setAddOpen((current) => !current)}>
          <Plus className="mr-1 h-4 w-4" />
          Add
        </Button>
      </header>

      {addOpen && (
        <form
          className="space-y-2 rounded-lg border border-border/60 bg-card px-4 py-4"
          onSubmit={(event) => {
            event.preventDefault()
            if (title.trim()) create.mutate()
          }}
        >
          <Input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Title, e.g. 'Furnace filter size'"
            aria-label="Knowledge title"
            disabled={create.isPending}
          />
          <Input
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            placeholder="Category (optional), e.g. 'warranty'"
            aria-label="Knowledge category"
            disabled={create.isPending}
          />
          <textarea
            value={content}
            onChange={(event) => setContent(event.target.value)}
            placeholder="Content"
            aria-label="Knowledge content"
            disabled={create.isPending}
            rows={4}
            className={cn(
              'flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background',
              'placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
              'disabled:cursor-not-allowed disabled:opacity-50',
            )}
          />
          <div className="flex gap-2">
            <Button type="submit" size="sm" disabled={!title.trim() || create.isPending}>
              {create.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Save'}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setAddOpen(false)}
              disabled={create.isPending}
            >
              Cancel
            </Button>
          </div>
          {create.isError && (
            <p className="rounded border border-red-300 bg-red-50 px-2 py-1 text-xs text-red-700">
              {create.error instanceof LifeOpsError
                ? create.error.message
                : 'Could not save that.'}
            </p>
          )}
        </form>
      )}

      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search knowledge…"
          aria-label="Search knowledge"
          className="pl-9"
        />
      </div>

      {knowledgeQuery.isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading…
        </div>
      ) : items.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border/60 px-4 py-8 text-center text-sm text-muted-foreground">
          {query ? `No knowledge matches “${query}”.` : 'No knowledge recorded yet.'}
        </p>
      ) : (
        <div className="space-y-2">
          {items.map((item) => (
            <KnowledgeCard key={item.id} item={item} />
          ))}
        </div>
      )}
    </div>
  )
}
