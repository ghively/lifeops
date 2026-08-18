/**
 * Search — universal search across LifeOps (BUILD_SPEC section 19).
 *
 * All twelve of the section's categories: people, preferences, tasks,
 * providers, assets, appointments, events, memory, documents, knowledge,
 * bills, actions, and historical facts (the durable audit log).
 *
 * Tasks, documents, and knowledge link to their own screens; actions and
 * historical facts link to Activity, which already renders both in full.
 * The rest render as plain rows: providers, assets, appointments, events,
 * memory, and bills have no dedicated Console screen to link to yet.
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Loader2, Search } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { QueryError } from '@/components/QueryError'
import {
  ACTION_TYPE_LABELS,
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
    results.tasks.length === 0 &&
    results.providers.length === 0 &&
    results.assets.length === 0 &&
    results.appointments.length === 0 &&
    results.events.length === 0 &&
    results.memories.length === 0 &&
    results.documents.length === 0 &&
    results.knowledge.length === 0 &&
    results.bills.length === 0 &&
    results.actions.length === 0 &&
    results.historical_facts.length === 0

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-8">
      <header>
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <Search className="h-5 w-5" />
          Search
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Search across people, preferences, tasks, providers, assets,
          appointments, events, memory, documents, knowledge, bills, actions,
          and historical facts.
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
          Search people, preferences, tasks, providers, assets, appointments,
          events, memory, documents, knowledge, bills, actions, and
          historical facts.
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

          {results.providers.length > 0 && (
            <section className="space-y-2">
              <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                Providers
              </h2>
              <div className="space-y-2">
                {results.providers.map((provider) => (
                  <div
                    key={provider.id}
                    className="rounded-lg border border-border/60 px-4 py-3"
                  >
                    <p className="font-medium">{provider.display_name}</p>
                  </div>
                ))}
              </div>
            </section>
          )}

          {results.assets.length > 0 && (
            <section className="space-y-2">
              <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                Assets
              </h2>
              <div className="space-y-2">
                {results.assets.map((asset) => (
                  <div
                    key={asset.id}
                    className="rounded-lg border border-border/60 px-4 py-3"
                  >
                    <p className="font-medium">{asset.display_name}</p>
                  </div>
                ))}
              </div>
            </section>
          )}

          {results.appointments.length > 0 && (
            <section className="space-y-2">
              <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                Appointments
              </h2>
              <div className="space-y-2">
                {results.appointments.map((appointment) => (
                  <div
                    key={appointment.id}
                    className="rounded-lg border border-border/60 px-4 py-3"
                  >
                    <p className="font-medium">{appointment.subject}</p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {appointment.start_at}
                    </p>
                  </div>
                ))}
              </div>
            </section>
          )}

          {results.events.length > 0 && (
            <section className="space-y-2">
              <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                Events
              </h2>
              <div className="space-y-2">
                {results.events.map((event) => (
                  <div
                    key={event.id}
                    className="rounded-lg border border-border/60 px-4 py-3"
                  >
                    <p className="font-medium">{event.display_name}</p>
                  </div>
                ))}
              </div>
            </section>
          )}

          {results.memories.length > 0 && (
            <section className="space-y-2">
              <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                Memory
              </h2>
              <div className="space-y-2">
                {results.memories.map((memory) => (
                  <div
                    key={memory.id}
                    className="rounded-lg border border-border/60 px-4 py-3"
                  >
                    <p className="font-medium">{memory.content}</p>
                  </div>
                ))}
              </div>
            </section>
          )}

          {results.documents.length > 0 && (
            <section className="space-y-2">
              <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                Documents
              </h2>
              <div className="space-y-2">
                {results.documents.map((document) => (
                  <Link
                    key={document.id}
                    to="/files"
                    className="block rounded-lg border border-border/60 px-4 py-3 transition-colors hover:bg-muted/50"
                  >
                    <p className="font-medium">{document.title}</p>
                    {document.summary && (
                      <p className="mt-1 text-sm text-muted-foreground">
                        {document.summary}
                      </p>
                    )}
                  </Link>
                ))}
              </div>
            </section>
          )}

          {results.knowledge.length > 0 && (
            <section className="space-y-2">
              <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                Knowledge
              </h2>
              <div className="space-y-2">
                {results.knowledge.map((item) => (
                  <Link
                    key={item.id}
                    to="/knowledge"
                    className="block rounded-lg border border-border/60 px-4 py-3 transition-colors hover:bg-muted/50"
                  >
                    <p className="font-medium">{item.title}</p>
                    {item.content && (
                      <p className="mt-1 text-sm text-muted-foreground">
                        {item.content}
                      </p>
                    )}
                  </Link>
                ))}
              </div>
            </section>
          )}

          {results.bills.length > 0 && (
            <section className="space-y-2">
              <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                Bills
              </h2>
              <div className="space-y-2">
                {results.bills.map((bill) => (
                  <div
                    key={bill.id}
                    className="rounded-lg border border-border/60 px-4 py-3"
                  >
                    <p className="font-medium">{bill.description}</p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {bill.amount} {bill.currency}
                    </p>
                  </div>
                ))}
              </div>
            </section>
          )}

          {results.actions.length > 0 && (
            <section className="space-y-2">
              <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                Actions
              </h2>
              <div className="space-y-2">
                {results.actions.map((action) => (
                  <Link
                    key={action.id}
                    to="/activity"
                    className="block rounded-lg border border-border/60 px-4 py-3 transition-colors hover:bg-muted/50"
                  >
                    <p className="font-medium">
                      {ACTION_TYPE_LABELS[action.type] ?? action.type}
                    </p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {action.status}
                      {action.failure_reason ? ` — ${action.failure_reason}` : ''}
                    </p>
                  </Link>
                ))}
              </div>
            </section>
          )}

          {results.historical_facts.length > 0 && (
            <section className="space-y-2">
              <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                Historical facts
              </h2>
              <div className="space-y-2">
                {results.historical_facts.map((record) => (
                  <Link
                    key={record.id}
                    to="/activity"
                    className="block rounded-lg border border-border/60 px-4 py-3 transition-colors hover:bg-muted/50"
                  >
                    <p className="font-medium">{record.intent ?? record.result}</p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {record.result}
                    </p>
                  </Link>
                ))}
              </div>
            </section>
          )}
        </div>
      ) : null}
    </div>
  )
}
