/**
 * Search — universal search across LifeOps (BUILD_SPEC section 19).
 *
 * Phase 1 searches people, preferences, and tasks through LifeOps Core's
 * `/search` endpoint. Memory, documents, knowledge, and the other result
 * kinds in the spec arrive as their phases land; the screen says so instead
 * of implying they were searched and found nothing.
 *
 * Tasks link to the Tasks screen. People and preferences have no dedicated
 * screen in Phase 1, so they render as plain rows rather than links to a
 * placeholder.
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Loader2, Search } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { QueryError } from '@/components/QueryError'
import {
  TASK_STATE_LABELS,
  errorMessage,
  searchApi,
} from '@/services/lifeops'

export function SearchPage() {
  const [input, setInput] = useState('')
  const [query, setQuery] = useState('')

  const searchQuery = useQuery({
    queryKey: ['lifeops', 'search', query],
    queryFn: () => searchApi.search(query),
    enabled: query.length > 0,
  })

  const results = searchQuery.data
  const isEmpty =
    results !== undefined &&
    results.people.length === 0 &&
    results.preferences.length === 0 &&
    results.tasks.length === 0

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-8">
      <header>
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <Search className="h-5 w-5" />
          Search
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Search across the people, preferences, and tasks LifeOps holds.
        </p>
      </header>

      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          const q = input.trim()
          if (q) setQuery(q)
        }}
      >
        <Input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Search LifeOps…"
          aria-label="Search query"
        />
        <Button type="submit" disabled={!input.trim()}>
          <Search className="h-4 w-4" />
          <span className="ml-1">Search</span>
        </Button>
      </form>

      {query.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border/60 px-4 py-8 text-center text-sm text-muted-foreground">
          Search people, preferences, and tasks.
        </p>
      ) : searchQuery.isError ? (
        <QueryError
          message={errorMessage(searchQuery.error)}
          onRetry={() => void searchQuery.refetch()}
        />
      ) : searchQuery.isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Searching…
        </div>
      ) : isEmpty ? (
        <p className="rounded-lg border border-dashed border-border/60 px-4 py-8 text-center text-sm text-muted-foreground">
          No results for “{query}”.
        </p>
      ) : results ? (
        <div className="space-y-6">
          {results.people.length > 0 && (
            <section className="space-y-2">
              <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                People
              </h2>
              <div className="space-y-2">
                {results.people.map((person) => (
                  <div
                    key={person.id}
                    className="rounded-lg border border-border/60 px-4 py-3"
                  >
                    <p className="font-medium">{person.display_name}</p>
                    {person.aliases.length > 0 && (
                      <p className="mt-1 text-sm text-muted-foreground">
                        also known as {person.aliases.join(', ')}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}

          {results.preferences.length > 0 && (
            <section className="space-y-2">
              <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                Preferences
              </h2>
              <div className="space-y-2">
                {results.preferences.map((preference) => (
                  <div
                    key={preference.id}
                    className="rounded-lg border border-border/60 px-4 py-3"
                  >
                    <p className="font-medium">{preference.key}</p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {preference.value}
                    </p>
                  </div>
                ))}
              </div>
            </section>
          )}

          {results.tasks.length > 0 && (
            <section className="space-y-2">
              <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                Tasks
              </h2>
              <div className="space-y-2">
                {results.tasks.map((task) => (
                  <Link
                    key={task.id}
                    to="/tasks"
                    className="block rounded-lg border border-border/60 px-4 py-3 transition-colors hover:bg-muted/50"
                  >
                    <p className="font-medium">{task.title}</p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {TASK_STATE_LABELS[task.state]}
                    </p>
                  </Link>
                ))}
              </div>
            </section>
          )}
        </div>
      ) : null}

      <footer className="rounded-lg border border-dashed border-border/60 px-4 py-4 text-sm text-muted-foreground">
        <p className="font-medium text-foreground">Phase 1</p>
        <p className="mt-1">
          Memory, documents, knowledge, providers, and the rest of the world
          model join search as their phases land.
        </p>
      </footer>
    </div>
  )
}
