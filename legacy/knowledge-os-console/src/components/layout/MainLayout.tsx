import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  PanelLeft,
  Search,
  Bell,
  Plus,
  Settings2,
  Download,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Sidebar } from './Sidebar'
import { type AgentItem } from '@/services/api'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { useInstallPrompt } from '@/hooks/useInstallPrompt'
import { useAgentNotifications } from '@/hooks/useAgentNotifications'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'

interface MainLayoutProps {
  children: React.ReactNode
}

// Map top-level route prefixes to human labels for the crumb trail.
const ROUTE_LABELS: Array<{ prefix: string; label: string; accent?: boolean }> = [
  { prefix: '/tasks', label: 'Tasks' },
  { prefix: '/files', label: 'Files' },
  { prefix: '/agents', label: 'Agents' },
  { prefix: '/settings', label: 'Settings' },
  { prefix: '/logs', label: 'Logs' },
  { prefix: '/search', label: 'Search' },
  { prefix: '/object', label: 'Notes', accent: true },
  { prefix: '/', label: 'Today', accent: true },
]

function resolveCrumbs(pathname: string, search: string) {
  if (pathname === '/' || pathname === '') {
    return [
      { label: 'Spaces', accent: false, current: false },
      { label: 'Today', accent: true, current: true },
    ]
  }
  const match = ROUTE_LABELS.find((r) => pathname.startsWith(r.prefix))
  if (!match) {
    return [{ label: 'Spaces', accent: false, current: true }]
  }
  const crumbs: Array<{ label: string; accent: boolean; current: boolean }> = [
    { label: 'Spaces', accent: false, current: false },
    { label: match.label, accent: !!match.accent, current: true },
  ]
  if (match.prefix === '/tasks' && search.includes('filter=today')) {
    crumbs.push({ label: 'Today', accent: true, current: true })
  }
  return crumbs
}

export function MainLayout({ children }: MainLayoutProps) {
  const { isAuthenticated } = useAuthStore()
  const { toggleTweaks } = useThemeStore()
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const isMobile = useMediaQuery('(max-width: 1023px)')
  const { canInstall, install } = useInstallPrompt()
  const navigate = useNavigate()
  const location = useLocation()
  useAgentNotifications(isAuthenticated)

  const [notifStatus, setNotifStatus] = useState<string | null>(null)
  const notifTimerRef = useRef<ReturnType<typeof setTimeout>>()

  const clearNotifTimer = () => {
    if (notifTimerRef.current) {
      clearTimeout(notifTimerRef.current)
      notifTimerRef.current = undefined
    }
  }

  useEffect(() => {
    if (!isMobile) setMobileSidebarOpen(false)
    return () => clearNotifTimer()
  }, [isMobile])

  const handleAgentClick = (agent: AgentItem) => {
    setMobileSidebarOpen(false)
    navigate(`/agents/${encodeURIComponent(agent.name)}/chat`)
  }

  const handleSearchSubmit = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && searchQuery.trim()) {
      navigate(`/search?q=${encodeURIComponent(searchQuery)}`)
    }
  }

  const handleNotificationsClick = async () => {
    if (!('Notification' in window)) {
      setNotifStatus('unsupported')
      clearNotifTimer()
      notifTimerRef.current = setTimeout(() => setNotifStatus(null), 3000)
      return
    }
    if (Notification.permission === 'default') {
      try {
        const result = await Notification.requestPermission()
        setNotifStatus(result === 'granted' ? 'enabled' : 'denied')
      } catch {
        setNotifStatus('blocked')
      }
    } else if (Notification.permission === 'granted') {
      setNotifStatus('already')
    } else {
      setNotifStatus('blocked')
    }
    clearNotifTimer()
    notifTimerRef.current = setTimeout(() => setNotifStatus(null), 3000)
  }

  const NOTIF_STATUS_LABELS: Record<string, string> = {
    enabled: 'Notifications enabled',
    already: 'Notifications already on',
    denied: 'Notifications denied',
    blocked: 'Notifications blocked — enable them in browser settings',
    unsupported: 'Notifications not supported in this browser',
  }

  const crumbs = resolveCrumbs(location.pathname, location.search)
  const notifsOn =
    notifStatus === 'enabled' ||
    notifStatus === 'already' ||
    (typeof Notification !== 'undefined' &&
      Notification.permission === 'granted')

  return (
    <div
      className="flex"
      style={{
        height: '100vh',
        width: '100%',
        background: 'var(--bg)',
        overflow: 'hidden',
      }}
    >
      <Sidebar
        collapsed={isMobile ? false : sidebarCollapsed}
        isMobile={isMobile}
        mobileOpen={mobileSidebarOpen}
        onToggle={() => {
          if (isMobile) {
            setMobileSidebarOpen((o) => !o)
            return
          }
          setSidebarCollapsed((c) => !c)
        }}
        onAgentClick={handleAgentClick}
        onNavigate={() => setMobileSidebarOpen(false)}
      />

      <div
        className={cn('flex flex-1 min-w-0 flex-col')}
        style={{ background: 'var(--bg)' }}
      >
        {/* Topbar */}
        <header className="kos-topbar">
          {isMobile && (
            <button
              type="button"
              aria-label="Toggle sidebar"
              data-testid="header-sidebar-toggle"
              onClick={() => setMobileSidebarOpen((o) => !o)}
              className="kos-icon-btn"
            >
              <PanelLeft size={16} />
            </button>
          )}

          <div className="kos-crumbs">
            {crumbs.map((c, i) => (
              <span key={`${c.label}-${i}`} style={{ display: 'inline-flex', gap: 8 }}>
                <span
                  className={cn(
                    c.current && 'cur',
                    c.current && c.accent && 'cur-accent',
                  )}
                >
                  {c.label}
                </span>
                {i < crumbs.length - 1 && <span>/</span>}
              </span>
            ))}
          </div>

          <label className="kos-search">
            <Search size={15} style={{ opacity: 0.7 }} />
            <input
              type="text"
              placeholder="Search notes, tasks, files, agents…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={handleSearchSubmit}
              aria-label="Search"
            />
            <span className="kos-kbd">⌘K</span>
          </label>

          <div
            className="kos-top-actions"
            style={{ display: 'flex', alignItems: 'center', gap: 4 }}
          >
            {canInstall && (
              <button
                type="button"
                aria-label="Install app"
                className="kos-icon-btn"
                onClick={() => void install()}
                title="Install"
              >
                <Download size={15} />
              </button>
            )}
            <button
              type="button"
              aria-label="New"
              className="kos-icon-btn"
              title="New"
              onClick={() => navigate('/')}
            >
              <Plus size={16} />
            </button>
            <button
              type="button"
              aria-label="Notifications"
              data-testid="header-notifications-btn"
              className={cn('kos-icon-btn', notifsOn && 'kos-dot-badge')}
              onClick={() => void handleNotificationsClick()}
              title="Notifications"
            >
              <Bell size={16} />
            </button>
            {notifStatus && NOTIF_STATUS_LABELS[notifStatus] && (
              <span
                role="status"
                aria-live="polite"
                data-testid="notif-status"
                style={{
                  fontSize: 12,
                  opacity: 0.75,
                  padding: '2px 8px',
                  borderRadius: 999,
                  background: 'var(--surface, rgba(0,0,0,0.06))',
                  whiteSpace: 'nowrap',
                }}
              >
                {NOTIF_STATUS_LABELS[notifStatus]}
              </span>
            )}
            <button
              type="button"
              aria-label="Tweaks"
              className="kos-icon-btn"
              onClick={toggleTweaks}
              title="Tweaks"
            >
              <Settings2 size={16} />
            </button>
          </div>
        </header>

        {/* Content */}
        <main className="flex-1 overflow-auto" style={{ background: 'var(--bg)' }}>
          {children}
        </main>
      </div>
    </div>
  )
}
