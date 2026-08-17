/**
 * LifeOps Console.
 *
 * The Knowledge-OS frontend, rewired onto LifeOps Core. Phase 1 routes:
 * Today, Needs Attention, Waiting, Tasks, Search, Configuration, System, and
 * Activity (BUILD_SPEC section 90); Phase 2 adds Memory and Phase 3 the World
 * graph. The remaining navigation entries route to a placeholder naming their
 * phase.
 *
 * Authentication: if LifeOps Core has Console auth enabled it answers 401 to
 * unauthenticated requests; the axios interceptor (services/lifeops.ts) then
 * flips the auth store and the whole shell swaps to LoginPage. When auth is
 * disabled server-side, the bootstrap `me()` call succeeds without a token
 * and the login screen never appears.
 */

import { useEffect } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router-dom'

import { ErrorBoundary } from './components/ErrorBoundary'
import { LifeOpsLayout } from './components/layout/LifeOpsLayout'
import { ThemeProvider } from './components/theme/ThemeProvider'
import { useAuthStore } from './lib/auth'
import { ActivityPage } from './pages/lifeops/ActivityPage'
import { ApprovalsPage } from './pages/lifeops/ApprovalsPage'
import { ComingInPhasePage } from './pages/lifeops/ComingInPhasePage'
import { ConfigurationPage } from './pages/lifeops/ConfigurationPage'
import { LoginPage } from './pages/lifeops/LoginPage'
import { MemoryPage } from './pages/lifeops/MemoryPage'
import { NeedsAttentionPage } from './pages/lifeops/NeedsAttentionPage'
import { SearchPage } from './pages/lifeops/SearchPage'
import { LifeOpsTasksPage } from './pages/lifeops/TasksPage'
import { SystemPage } from './pages/lifeops/SystemPage'
import { TodayPage } from './pages/lifeops/TodayPage'
import { WaitingPage } from './pages/lifeops/WaitingPage'
import { WorldPage } from './pages/lifeops/WorldPage'
import { LifeOpsError, authApi } from './services/lifeops'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 30,
      gcTime: 1000 * 60 * 10,
      retry: (failureCount, error) => {
        // A capability denial or a validation error will not become true on
        // retry; only transient failures are worth repeating.
        const status = (error as { status?: number })?.status
        if (status && status >= 400 && status < 500) return false
        return failureCount < 2
      },
      retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 5000),
      refetchOnWindowFocus: false,
      refetchOnReconnect: true,
    },
    mutations: { retry: 0 },
  },
})

/** Navigation entries that exist in the spec but land in a later phase. */
const PENDING_ROUTES: Array<{
  path: string
  title: string
  phase: number
  description: string
}> = [
  {
    path: '/calendar',
    title: 'Calendar',
    phase: 7,
    description: 'Availability, holds, and events linked to LifeOps entities.',
  },
  {
    path: '/knowledge',
    title: 'Knowledge',
    phase: 1,
    description: 'Reference material: policies, handbooks, contracts, and procedures.',
  },
  {
    path: '/files',
    title: 'Files',
    phase: 1,
    description: 'Documents indexed into the LifeOps knowledge corpus.',
  },
  {
    path: '/hermes',
    title: 'Hermes',
    phase: 1,
    description:
      'Live status of the assistant: model, MCP connection, memory provider, and voice.',
  },
]

/**
 * Find out whether this server wants a password. A 401 means login; success
 * means either a valid stored token or auth disabled — both are
 * "authenticated". A network failure means the server is down, and the
 * regular screens explain that better than a login form would.
 */
function useAuthBootstrap(): void {
  const setAuthenticated = useAuthStore((state) => state.setAuthenticated)
  const setUnauthenticated = useAuthStore((state) => state.setUnauthenticated)

  useEffect(() => {
    let cancelled = false
    authApi
      .me()
      .then(() => {
        if (!cancelled) setAuthenticated()
      })
      .catch((error: unknown) => {
        if (cancelled) return
        if (error instanceof LifeOpsError && error.status === 401) {
          setUnauthenticated()
        } else {
          setAuthenticated()
        }
      })
    return () => {
      cancelled = true
    }
  }, [setAuthenticated, setUnauthenticated])
}

function App() {
  const status = useAuthStore((state) => state.status)
  useAuthBootstrap()

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <ErrorBoundary>
          <BrowserRouter>
            {status === 'unknown' ? null : status === 'unauthenticated' ? (
              <LoginPage />
            ) : (
              <LifeOpsLayout>
                <Routes>
                  <Route path="/" element={<TodayPage />} />
                  <Route path="/needs-attention" element={<NeedsAttentionPage />} />
                  <Route path="/approvals" element={<ApprovalsPage />} />
                  <Route path="/waiting" element={<WaitingPage />} />
                  <Route path="/tasks" element={<LifeOpsTasksPage />} />
                  <Route path="/search" element={<SearchPage />} />
                  <Route path="/memory" element={<MemoryPage />} />
                  <Route path="/world" element={<WorldPage />} />
                  <Route path="/configuration" element={<ConfigurationPage />} />
                  <Route path="/system" element={<SystemPage />} />
                  <Route path="/activity" element={<ActivityPage />} />

                  {PENDING_ROUTES.map((route) => (
                    <Route
                      key={route.path}
                      path={route.path}
                      element={
                        <ComingInPhasePage
                          title={route.title}
                          phase={route.phase}
                          description={route.description}
                        />
                      }
                    />
                  ))}

                  <Route
                    path="*"
                    element={
                      <ComingInPhasePage
                        title="Not found"
                        phase={0}
                        description="That screen does not exist in LifeOps Console."
                      />
                    }
                  />
                </Routes>
              </LifeOpsLayout>
            )}
          </BrowserRouter>
        </ErrorBoundary>
      </ThemeProvider>
    </QueryClientProvider>
  )
}

export default App
