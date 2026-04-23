import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import {
  PanelLeft,
  FileText,
  CheckSquare,
  Folder,
  Bot,
  Search,
  ChevronDown,
  Settings,
  ScrollText,
  Calendar,
  Inbox,
  LogOut,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useQuery } from '@tanstack/react-query'
import {
  agentsApi,
  objectsApi,
  settingsApi,
  tasksApi,
  type AgentItem,
  type ObjectItem,
  type TaskItem,
} from '@/services/api'
import { useAuthStore } from '@/stores/auth'

interface SidebarProps {
  collapsed: boolean
  isMobile?: boolean
  mobileOpen?: boolean
  onToggle: () => void
  onAgentClick?: (agent: AgentItem) => void
  onNavigate?: () => void
}

const quickLinks = [
  { id: 'today', name: 'Today', icon: Calendar, href: '/tasks?filter=today' },
  { id: 'inbox', name: 'Inbox', icon: Inbox, href: '/inbox' },
]

const spaces = [
  { id: 'home', name: 'Notes', icon: FileText, href: '/' },
  { id: 'tasks', name: 'Tasks', icon: CheckSquare, href: '/tasks' },
  { id: 'files', name: 'Files', icon: Folder, href: '/files' },
  { id: 'agents', name: 'Agents', icon: Bot, href: '/agents' },
  { id: 'search', name: 'Search', icon: Search, href: '/search' },
]

const agentDotClass = (status: AgentItem['status']) => {
  switch (status) {
    case 'active':
    case 'busy':
    case 'working':
      return 'kos-agent-dot'
    case 'error':
      return 'kos-agent-dot error'
    case 'idle':
    case 'offline':
    default:
      return 'kos-agent-dot idle'
  }
}

const avatarSeedColors = ['#7a5c3d,#3d2b18', '#6a6358,#3a362f', '#88613c,#39220f']

function initialsFrom(str: string): string {
  const trimmed = str.trim()
  if (!trimmed) return '??'
  const parts = trimmed.split(/\s+/)
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[1][0]).toUpperCase()
}

export function Sidebar({
  collapsed,
  isMobile = false,
  mobileOpen = false,
  onToggle,
  onAgentClick,
  onNavigate,
}: SidebarProps) {
  const location = useLocation()
  const { user } = useAuthStore()
  const [spacesCollapsed, setSpacesCollapsed] = useState(false)
  const [agentsCollapsed, setAgentsCollapsed] = useState(false)
  const [foldersCollapsed, setFoldersCollapsed] = useState(false)

  const { data: agentsData } = useQuery({
    queryKey: ['agents'],
    queryFn: agentsApi.list,
    refetchInterval: 10000,
  })
  const agents: AgentItem[] = agentsData?.agents ?? []

  const { data: watchedFoldersData } = useQuery({
    queryKey: ['watched-folders'],
    queryFn: settingsApi.getWatchedFolders,
  })
  const watchedFolders = watchedFoldersData?.folders ?? []

  const { data: recentObjectsData } = useQuery({
    queryKey: ['objects', { limit: 6 }],
    queryFn: () => objectsApi.list({ limit: 6 }),
  })
  const recentObjects: ObjectItem[] = recentObjectsData?.objects ?? []

  const { data: tasksData } = useQuery({
    queryKey: ['tasks', 'sidebar-counts'],
    queryFn: () => tasksApi.list(),
    staleTime: 30_000,
    refetchInterval: 60_000,
  })
  const tasks: TaskItem[] = (tasksData?.tasks ?? []) as TaskItem[]

  const totalObjects = recentObjectsData?.total ?? recentObjects.length
  const agentCount = agents.length

  // Today = tasks due today or overdue and not yet done
  const endOfToday = (() => {
    const d = new Date()
    d.setHours(23, 59, 59, 999)
    return d
  })()
  const todayCount = tasks.filter((t) => {
    const status = t.properties?.status
    if (status === 'done') return false
    const due = t.properties?.due_date
    if (!due) return false
    const parsed = new Date(due)
    return !Number.isNaN(parsed.getTime()) && parsed <= endOfToday
  }).length

  // Inbox = tasks still in `todo` with no due date (unprocessed)
  const inboxCount = tasks.filter((t) => {
    const status = t.properties?.status
    return status === 'todo' && !t.properties?.due_date
  }).length

  if (!isMobile && collapsed) {
    return (
      <aside
        className="kos-sidebar flex flex-col items-center py-3 px-2"
        style={{ width: 56, flex: 'none' }}
      >
        <button
          type="button"
          aria-label="Toggle sidebar"
          data-testid="sidebar-toggle"
          onClick={onToggle}
          className="kos-icon-btn mb-3"
        >
          <PanelLeft size={16} />
        </button>
        <div className="flex flex-col gap-1">
          {spaces.map((s) => (
            <Link
              key={s.id}
              to={s.href}
              onClick={onNavigate}
              className={cn(
                'kos-icon-btn',
                location.pathname === s.href && 'active-collapsed',
              )}
              style={{
                color:
                  location.pathname === s.href
                    ? 'var(--accent)'
                    : undefined,
              }}
              aria-label={s.name}
              title={s.name}
            >
              <s.icon size={16} />
            </Link>
          ))}
        </div>
      </aside>
    )
  }

  return (
    <>
      {isMobile && mobileOpen && (
        <button
          type="button"
          aria-label="Close navigation"
          className="fixed inset-0 z-30 bg-black/40 lg:hidden"
          onClick={onToggle}
        />
      )}
      <aside
        className={cn(
          'kos-sidebar flex flex-col',
          isMobile
            ? 'fixed inset-y-0 left-0 z-40 w-[min(85vw,18rem)] shadow-xl transition-transform duration-200'
            : 'w-72',
          isMobile && (mobileOpen ? 'translate-x-0' : '-translate-x-full'),
        )}
        style={!isMobile ? { flex: 'none', width: 288 } : undefined}
      >
        {/* Brand */}
        <div
          className="flex items-center justify-between"
          style={{
            padding: '20px 20px 16px',
            borderBottom: '1px solid var(--sidebar-hair)',
          }}
        >
          <Link
            to="/"
            onClick={onNavigate}
            className="kos-brand-mark"
            style={{ textDecoration: 'none' }}
          >
            <span className="kos-brand-glyph">K</span>
            <div>
              <div>
                Knowledge <em>OS</em>
              </div>
              <div className="kos-brand-sub">v0.2 · personal</div>
            </div>
          </Link>
          <button
            type="button"
            aria-label="Toggle sidebar"
            data-testid="sidebar-toggle"
            onClick={onToggle}
            className="kos-icon-btn"
            title="Collapse"
          >
            <PanelLeft size={15} />
          </button>
        </div>

        {/* Scrollable nav */}
        <ScrollArea className="flex-1 kos-scroll">
          <div style={{ padding: '14px 10px 10px' }}>
            {/* Quick links */}
            <nav style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              {quickLinks.map((q) => {
                const active = location.pathname + location.search === q.href
                return (
                  <Link
                    key={q.id}
                    to={q.href}
                    onClick={onNavigate}
                    className={cn('kos-nav-item', active && 'active')}
                    style={{ textDecoration: 'none' }}
                  >
                    <q.icon className="kos-nav-ico" size={16} />
                    <span>{q.name}</span>
                    {q.id === 'today' && todayCount > 0 && (
                      <span className="kos-nav-count">{todayCount}</span>
                    )}
                    {q.id === 'inbox' && inboxCount > 0 && (
                      <span className="kos-nav-count">{inboxCount}</span>
                    )}
                  </Link>
                )
              })}
            </nav>

            {/* Spaces */}
            <button
              type="button"
              className={cn('kos-section-head w-full', spacesCollapsed && 'collapsed')}
              onClick={() => setSpacesCollapsed((v) => !v)}
            >
              <span>Spaces</span>
              <ChevronDown className="kos-chev kos-nav-ico" size={14} />
            </button>
            {!spacesCollapsed && (
              <nav style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                {spaces.map((s) => {
                  const active = location.pathname === s.href
                  const count =
                    s.id === 'home'
                      ? totalObjects
                      : s.id === 'agents'
                      ? agentCount
                      : undefined
                  return (
                    <Link
                      key={s.id}
                      to={s.href}
                      onClick={onNavigate}
                      className={cn('kos-nav-item', active && 'active')}
                      style={{ textDecoration: 'none' }}
                    >
                      <s.icon className="kos-nav-ico" size={16} />
                      <span>{s.name}</span>
                      {count !== undefined && (
                        <span className="kos-nav-count">{count}</span>
                      )}
                    </Link>
                  )
                })}
              </nav>
            )}

            {/* Agents */}
            <button
              type="button"
              className={cn('kos-section-head w-full', agentsCollapsed && 'collapsed')}
              onClick={() => setAgentsCollapsed((v) => !v)}
            >
              <span>Agents</span>
              <ChevronDown className="kos-chev kos-nav-ico" size={14} />
            </button>
            {!agentsCollapsed && (
              <nav style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                {agents.length === 0 ? (
                  <div
                    style={{
                      padding: '6px 12px',
                      fontSize: 12,
                      color: 'var(--sidebar-mute)',
                    }}
                  >
                    No agents configured
                  </div>
                ) : (
                  agents.map((agent) => {
                    const isLive =
                      agent.status === 'active' ||
                      agent.status === 'busy' ||
                      agent.status === 'working'
                    return (
                      <button
                        key={agent.id}
                        type="button"
                        className="kos-nav-item"
                        onClick={() => onAgentClick?.(agent)}
                      >
                        <span className={agentDotClass(agent.status)} />
                        <span>
                          <span className="kos-hand">@</span>
                          {agent.name}
                        </span>
                        {isLive && <span className="kos-nav-count">live</span>}
                      </button>
                    )
                  })
                )}
              </nav>
            )}

            {/* Recent Objects */}
            <div className="kos-section-head">
              <span>Recent Objects</span>
            </div>
            <div style={{ padding: '2px 4px' }}>
              {recentObjects.length === 0 ? (
                <div
                  style={{
                    padding: '6px 10px',
                    fontSize: 12,
                    color: 'var(--sidebar-mute)',
                  }}
                >
                  No recent objects
                </div>
              ) : (
                recentObjects.slice(0, 4).map((obj, i) => (
                  <Link
                    key={obj.id}
                    to={`/object/${obj.id}`}
                    onClick={onNavigate}
                    className="kos-recent-row"
                  >
                    <div
                      className="kos-avatar"
                      style={
                        i === 0
                          ? undefined
                          : {
                              background: `linear-gradient(135deg,${
                                avatarSeedColors[i % avatarSeedColors.length]
                              })`,
                            }
                      }
                    >
                      {initialsFrom(obj.title || obj.type || 'NO')}
                    </div>
                    <div style={{ minWidth: 0 }}>
                      <div className="kos-recent-name truncate">
                        {obj.title || 'Untitled'}
                      </div>
                      <div className="kos-recent-sub truncate">
                        {obj.type}
                      </div>
                    </div>
                  </Link>
                ))
              )}
            </div>

            {/* Watched folders */}
            {watchedFolders.length > 0 && (
              <>
                <button
                  type="button"
                  className={cn(
                    'kos-section-head w-full',
                    foldersCollapsed && 'collapsed',
                  )}
                  onClick={() => setFoldersCollapsed((v) => !v)}
                >
                  <span>Watched Folders</span>
                  <ChevronDown className="kos-chev kos-nav-ico" size={14} />
                </button>
                {!foldersCollapsed && (
                  <nav style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                    {watchedFolders.map(
                      (folder: { path: string; id: string }) => (
                        <div key={folder.id} className="kos-nav-item">
                          <Folder className="kos-nav-ico" size={16} />
                          <span className="truncate">{folder.path}</span>
                        </div>
                      ),
                    )}
                  </nav>
                )}
              </>
            )}
          </div>
        </ScrollArea>

        {/* Footer */}
        <div
          style={{
            borderTop: '1px solid var(--sidebar-hair)',
            padding: 10,
            display: 'flex',
            flexDirection: 'column',
            gap: 2,
          }}
        >
          {user && (
            <div
              style={{
                padding: '6px 10px 8px',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}
            >
              <div className="kos-avatar">
                {initialsFrom(user.display_name || user.username || user.email || 'U')}
              </div>
              <div style={{ minWidth: 0 }}>
                <div className="kos-recent-name truncate">
                  {user.display_name || user.username}
                </div>
                <div className="kos-recent-sub truncate">{user.email}</div>
              </div>
            </div>
          )}
          <Link
            to="/settings"
            onClick={onNavigate}
            className={cn(
              'kos-nav-item',
              location.pathname === '/settings' && 'active',
            )}
            style={{ textDecoration: 'none' }}
          >
            <Settings className="kos-nav-ico" size={16} />
            <span>Settings</span>
          </Link>
          <Link
            to="/logs"
            onClick={onNavigate}
            className={cn(
              'kos-nav-item',
              location.pathname === '/logs' && 'active',
            )}
            style={{ textDecoration: 'none' }}
          >
            <ScrollText className="kos-nav-ico" size={16} />
            <span>Logs</span>
          </Link>
          <button
            type="button"
            aria-label="Logout"
            className="kos-nav-item"
            onClick={() => useAuthStore.getState().logout()}
          >
            <LogOut className="kos-nav-ico" size={16} />
            <span>Logout</span>
          </button>
        </div>
      </aside>
    </>
  )
}
