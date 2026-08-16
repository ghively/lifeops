/**
 * LifeOps Console.
 *
 * The Knowledge-OS frontend, rewired onto LifeOps Core. Only the Phase 0
 * screens are routed: Today, Tasks, Configuration, and System. The remaining
 * navigation entries route to a placeholder naming their phase.
 *
 * Authentication: Phase 0 has no login. LifeOps Core binds to 127.0.0.1 and
 * Phase 0 grants it no external-write capability, so the exposure is a local
 * process on a personal machine. Console auth returns in Phase 1 alongside the
 * rest of the Console foundation — see SECURITY.md.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router-dom'

import { ErrorBoundary } from './components/ErrorBoundary'
import { LifeOpsLayout } from './components/layout/LifeOpsLayout'
import { ThemeProvider } from './components/theme/ThemeProvider'
import { ComingInPhasePage } from './pages/lifeops/ComingInPhasePage'
import { ConfigurationPage } from './pages/lifeops/ConfigurationPage'
import { LifeOpsTasksPage } from './pages/lifeops/TasksPage'
import { SystemPage } from './pages/lifeops/SystemPage'
import { TodayPage } from './pages/lifeops/TodayPage'

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
    path: '/needs-attention',
    title: 'Needs Attention',
    phase: 1,
    description:
      'Approvals, clarifications, MFA prompts, and failed actions — only what genuinely needs a human.',
  },
  {
    path: '/waiting',
    title: 'Waiting',
    phase: 4,
    description:
      'Work blocked on another person, organisation, or future event, with follow-up state.',
  },
  {
    path: '/calendar',
    title: 'Calendar',
    phase: 7,
    description: 'Availability, holds, and events linked to LifeOps entities.',
  },
  {
    path: '/world',
    title: 'World',
    phase: 3,
    description:
      'The interactive graph of people, providers, assets, and their relationships.',
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
    path: '/memory',
    title: 'Memory',
    phase: 2,
    description:
      'Persistent assistant memory, made inspectable and correctable with full provenance.',
  },
  {
    path: '/hermes',
    title: 'Hermes',
    phase: 1,
    description:
      'Live status of the assistant: model, MCP connection, memory provider, and voice.',
  },
  {
    path: '/activity',
    title: 'Activity',
    phase: 1,
    description: 'A human-readable audit trail of what the assistant did, and why.',
  },
]

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <ErrorBoundary>
          <BrowserRouter>
            <LifeOpsLayout>
              <Routes>
                <Route path="/" element={<TodayPage />} />
                <Route path="/tasks" element={<LifeOpsTasksPage />} />
                <Route path="/configuration" element={<ConfigurationPage />} />
                <Route path="/system" element={<SystemPage />} />

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
          </BrowserRouter>
        </ErrorBoundary>
      </ThemeProvider>
    </QueryClientProvider>
  )
}

export default App
