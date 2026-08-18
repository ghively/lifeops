/**
 * Files — references to documents ingested from email, the calendar, or
 * recorded by hand (BUILD_SPEC sections 18, 36, 64, 96).
 *
 * "Actual binary files remain in file/object storage" (section 18) — LifeOps
 * Core has no file-upload endpoint and never will store the bytes; this
 * screen records and lists the reference (title, source, a source-system id,
 * a summary), never a file. Recording is Console/HTTP-only, the same
 * boundary Knowledge draws; unlike Knowledge, Documents have no MCP surface
 * at all yet — reading here is the only way to see one today.
 */

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FileText, Loader2, Plus, Search } from 'lucide-react'

import { QueryError } from '@/components/QueryError'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  DOCUMENT_SOURCE_LABELS,
  LifeOpsError,
  documentsApi,
  errorMessage,
  type DocumentSource,
  type LifeOpsDocument,
} from '@/services/lifeops'

function formatDate(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function DocumentCard({ document }: { document: LifeOpsDocument }) {
  return (
    <div className="rounded-lg border border-border/60 bg-card px-4 py-3">
      <div className="flex items-start justify-between gap-4">
        <p className="font-medium">{document.title}</p>
        <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
          {DOCUMENT_SOURCE_LABELS[document.source as DocumentSource] ?? document.source}
        </span>
      </div>
      {document.summary && (
        <p className="mt-1.5 text-sm text-muted-foreground">{document.summary}</p>
      )}
      <p className="mt-2 text-xs text-muted-foreground">
        Recorded {formatDate(document.created_at)}
        {document.mime_type ? ` · ${document.mime_type}` : ''}
      </p>
    </div>
  )
}

export function FilesPage() {
  const queryClient = useQueryClient()
  const [query, setQuery] = useState('')
  const [addOpen, setAddOpen] = useState(false)
  const [title, setTitle] = useState('')
  const [source, setSource] = useState<DocumentSource>('manual')
  const [sourceRef, setSourceRef] = useState('')
  const [summary, setSummary] = useState('')

  const documentsQuery = useQuery({
    queryKey: ['lifeops', 'documents', query],
    queryFn: () => documentsApi.search({ q: query, limit: 200 }),
  })

  const create = useMutation({
    mutationFn: () =>
      documentsApi.create({
        title: title.trim(),
        source,
        source_ref: sourceRef.trim() || undefined,
        summary: summary.trim() || undefined,
      }),
    onSuccess: () => {
      setAddOpen(false)
      setTitle('')
      setSource('manual')
      setSourceRef('')
      setSummary('')
      void queryClient.invalidateQueries({ queryKey: ['lifeops', 'documents'] })
    },
  })

  if (documentsQuery.isError) {
    return (
      <div className="p-8">
        <QueryError
          message={errorMessage(documentsQuery.error)}
          onRetry={() => void documentsQuery.refetch()}
        />
      </div>
    )
  }

  const documents = documentsQuery.data?.documents ?? []

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-8">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <FileText className="h-5 w-5" />
            Files
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            References to things ingested from email or the calendar. LifeOps
            stores the reference and a summary, never the file itself.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => setAddOpen((current) => !current)}>
          <Plus className="mr-1 h-4 w-4" />
          Add reference
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
            placeholder="Title, e.g. 'ABC Electric quote'"
            aria-label="Document title"
            disabled={create.isPending}
          />
          <div className="flex gap-2">
            <select
              value={source}
              onChange={(event) => setSource(event.target.value as DocumentSource)}
              aria-label="Document source"
              disabled={create.isPending}
              className="w-40 rounded-md border border-input bg-background px-2 py-1.5 text-sm"
            >
              {(Object.keys(DOCUMENT_SOURCE_LABELS) as DocumentSource[]).map((key) => (
                <option key={key} value={key}>
                  {DOCUMENT_SOURCE_LABELS[key]}
                </option>
              ))}
            </select>
            <Input
              value={sourceRef}
              onChange={(event) => setSourceRef(event.target.value)}
              placeholder="Source reference (optional), e.g. a message id"
              aria-label="Source reference"
              disabled={create.isPending}
            />
          </div>
          <Input
            value={summary}
            onChange={(event) => setSummary(event.target.value)}
            placeholder="Summary (optional)"
            aria-label="Document summary"
            disabled={create.isPending}
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
          placeholder="Search files…"
          aria-label="Search files"
          className="pl-9"
        />
      </div>

      {documentsQuery.isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading…
        </div>
      ) : documents.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border/60 px-4 py-8 text-center text-sm text-muted-foreground">
          {query ? `No files match “${query}”.` : 'No file references recorded yet.'}
        </p>
      ) : (
        <div className="space-y-2">
          {documents.map((document) => (
            <DocumentCard key={document.id} document={document} />
          ))}
        </div>
      )}
    </div>
  )
}
