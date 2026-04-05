import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import {
  PanelLeft,
  FileText,
  CheckSquare,
  Folder,
  Bot,
  Search,
  Plus,
  ChevronRight,
  ChevronDown,
  Settings,
  Calendar,
  Inbox,
  Loader2,
  LogOut,
  User as UserIcon
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { useQuery } from '@tanstack/react-query'
import { agentsApi, objectsApi, settingsApi, type AgentItem, type ObjectItem } from '@/services/api'
import { useAuthStore } from '@/stores/auth'

interface SidebarProps {
  collapsed: boolean
  isMobile?: boolean
  mobileOpen?: boolean
  onToggle: () => void
  onAgentClick?: (agent: AgentItem) => void
  onNavigate?: () => void
}

const spaces = [
  { id: 'home', name: 'Home', icon: FileText, href: '/' },
  { id: 'tasks', name: 'Tasks', icon: CheckSquare, href: '/tasks' },
  { id: 'files', name: 'Files', icon: Folder, href: '/files' },
  { id: 'agents', name: 'Agents', icon: Bot, href: '/agents' },
  { id: 'search', name: 'Search', icon: Search, href: '/search' },
]

const quickLinks = [
  { id: 'today', name: 'Today', icon: Calendar, href: '/tasks?filter=today' },
  { id: 'inbox', name: 'Inbox', icon: Inbox, href: '/inbox' },
]

export function Sidebar({ collapsed, isMobile = false, mobileOpen = false, onToggle, onAgentClick, onNavigate }: SidebarProps) {
  const location = useLocation()
  const { user, logout } = useAuthStore()
  const [spacesOpen, setSpacesOpen] = useState(true)
  const [agentsOpen, setAgentsOpen] = useState(true)
  const [foldersOpen, setFoldersOpen] = useState(true)
  const [userMenuOpen, setUserMenuOpen] = useState(false)

  // Fetch agents
  const { data: agentsData, isLoading: agentsLoading } = useQuery({
    queryKey: ['agents'],
    queryFn: agentsApi.list,
    refetchInterval: 10000, // Poll every 10 seconds for status updates
  })
  const agents = agentsData?.agents ?? []

  // Fetch watched folders
  const { data: watchedFoldersData, isLoading: foldersLoading } = useQuery({
    queryKey: ['watched-folders'],
    queryFn: settingsApi.getWatchedFolders,
  })
  const watchedFolders = watchedFoldersData?.folders ?? []
  const { data: recentObjectsData, isLoading: objectsLoading } = useQuery({
    queryKey: ['objects', { limit: 8 }],
    queryFn: () => objectsApi.list({ limit: 8 }),
  })
  const recentObjects = recentObjectsData?.objects ?? []

  const getStatusColor = (status: AgentItem['status']) => {
    switch (status) {
      case 'active':
      case 'busy':
      case 'working': return 'bg-blue-500 animate-pulse'
      case 'idle': return 'bg-green-500'
      case 'error': return 'bg-red-500'
      case 'offline': return 'bg-gray-400'
      default: return 'bg-gray-400'
    }
  }

  const sidebarClasses = cn(
    'border-r bg-card flex flex-col',
    isMobile
      ? 'fixed inset-y-0 left-0 z-40 w-[min(85vw,20rem)] transform shadow-xl transition-transform duration-200'
      : collapsed
      ? 'w-14'
      : 'w-64',
    isMobile && (mobileOpen ? 'translate-x-0' : '-translate-x-full'),
  )

  if (!isMobile && collapsed) {
    return (
      <div className="w-14 border-r bg-card flex flex-col items-center py-4">
        <Button aria-label="Toggle sidebar" data-testid="sidebar-toggle" variant="ghost" size="icon" onClick={onToggle} className="mb-4">
          <PanelLeft className="h-5 w-5" />
        </Button>
        
        <div className="flex flex-col gap-2">
          {spaces.map((space) => (
            <Link key={space.id} to={space.href} onClick={onNavigate}>
              <Button
                variant={location.pathname === space.href ? 'secondary' : 'ghost'}
                size="icon"
                className="relative"
              >
                <space.icon className="h-5 w-5" />
              </Button>
            </Link>
          ))}
        </div>

        {/* Agent indicators */}
        <div className="mt-auto flex flex-col gap-2">
          {agents.slice(0, 3).map((agent: AgentItem) => (
            <Button
              key={agent.id}
              variant="ghost"
              size="icon"
              className="relative"
              onClick={() => onAgentClick?.(agent)}
            >
              <Bot className="h-5 w-5" />
              <span className={cn(
                "absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-card",
                getStatusColor(agent.status)
              )} />
            </Button>
          ))}
        </div>
      </div>
    )
  }

  return (
    <>
    {isMobile && mobileOpen && (
      <button
        type="button"
        aria-label="Close navigation"
        className="fixed inset-0 z-30 bg-black/35 lg:hidden"
        onClick={onToggle}
      />
    )}
    <div className={sidebarClasses}>
      {/* Header */}
      <div className="h-14 border-b flex items-center justify-between px-4">
        <Link to="/" className="font-semibold text-lg">
          Knowledge OS
        </Link>
        <Button aria-label="Toggle sidebar" data-testid="sidebar-toggle" variant="ghost" size="icon" onClick={onToggle}>
          <PanelLeft className="h-5 w-5" />
        </Button>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-3 space-y-4">
          {/* Quick Links */}
          <div className="space-y-1">
            {quickLinks.map((link) => (
              <Link key={link.id} to={link.href} onClick={onNavigate}>
                <Button
                  variant={location.pathname === link.href ? 'secondary' : 'ghost'}
                  className="w-full justify-start gap-2"
                >
                  <link.icon className="h-4 w-4" />
                  {link.name}
                </Button>
              </Link>
            ))}
          </div>

          {/* Spaces */}
          <Collapsible open={spacesOpen} onOpenChange={setSpacesOpen}>
            <CollapsibleTrigger asChild>
              <Button variant="ghost" className="w-full justify-between">
                <span className="text-sm font-medium text-muted-foreground">Spaces</span>
                {spacesOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <div className="space-y-1 pt-1">
                {spaces.map((space) => (
                  <Link key={space.id} to={space.href} onClick={onNavigate}>
                    <Button
                      variant={location.pathname === space.href ? 'secondary' : 'ghost'}
                      className="w-full justify-start gap-2"
                    >
                      <space.icon className="h-4 w-4" />
                      {space.name}
                    </Button>
                  </Link>
                ))}
              </div>
            </CollapsibleContent>
          </Collapsible>

          {/* Agents */}
          <Collapsible open={agentsOpen} onOpenChange={setAgentsOpen}>
            <CollapsibleTrigger asChild>
              <Button variant="ghost" className="w-full justify-between">
                <span className="text-sm font-medium text-muted-foreground">Agents</span>
                <div className="flex items-center gap-2">
                  {agentsLoading && <Loader2 className="h-3 w-3 animate-spin" />}
                  {agentsOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                </div>
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <div className="space-y-1 pt-1">
                {agentsLoading ? (
                  <div className="text-sm text-muted-foreground px-3 py-2">Loading agents...</div>
                ) : agents.length === 0 ? (
                  <div className="text-sm text-muted-foreground px-3 py-2">No agents configured</div>
                ) : (
                  agents.map((agent: AgentItem) => (
                    <Button
                      key={agent.id}
                      variant="ghost"
                      className="w-full justify-start gap-2"
                      onClick={() => onAgentClick?.(agent)}
                    >
                      <div className={cn("h-2 w-2 rounded-full flex-shrink-0", getStatusColor(agent.status))} />
                      <span className="truncate">@{agent.name}</span>
                      {agent.current_task && (
                        <span className="text-xs text-muted-foreground ml-auto truncate max-w-[60px]">
                          {agent.current_task}
                        </span>
                      )}
                    </Button>
                  ))
                )}
              </div>
            </CollapsibleContent>
          </Collapsible>

          <div>
            <div className="px-3 py-2 text-sm font-medium text-muted-foreground">
              Recent Objects
            </div>
            <div className="space-y-1">
              {objectsLoading ? (
                <div className="text-sm text-muted-foreground px-3 py-2">Loading objects...</div>
              ) : recentObjects.length === 0 ? (
                <div className="text-sm text-muted-foreground px-3 py-2">No recent objects</div>
              ) : (
                recentObjects.map((object: ObjectItem) => (
                  <Link key={object.id} to={`/object/${object.id}`} onClick={onNavigate}>
                    <Button variant="ghost" className="w-full justify-start gap-2">
                      <span>{object.icon || '📄'}</span>
                      <span className="truncate">{object.title}</span>
                    </Button>
                  </Link>
                ))
              )}
            </div>
          </div>

          {/* Watched Folders */}
          <Collapsible open={foldersOpen} onOpenChange={setFoldersOpen}>
            <CollapsibleTrigger asChild>
              <Button variant="ghost" className="w-full justify-between">
                <span className="text-sm font-medium text-muted-foreground">Watched Folders</span>
                <div className="flex items-center gap-2">
                  {foldersLoading && <Loader2 className="h-3 w-3 animate-spin" />}
                  {foldersOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                </div>
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <div className="space-y-1 pt-1">
                {foldersLoading ? (
                  <div className="text-sm text-muted-foreground px-3 py-2">Loading folders...</div>
                ) : watchedFolders.length === 0 ? (
                  <div className="text-sm text-muted-foreground px-3 py-2">No folders watched</div>
                ) : (
                  watchedFolders.map((folder: { path: string; id: string }) => (
                    <Button
                      key={folder.id}
                      variant="ghost"
                      className="w-full justify-start gap-2 text-sm"
                    >
                      <Folder className="h-4 w-4 flex-shrink-0" />
                      <span className="truncate">{folder.path}</span>
                    </Button>
                  ))
                )}
              </div>
            </CollapsibleContent>
          </Collapsible>
        </div>
      </ScrollArea>

      {/* Footer */}
      <div className="border-t p-3 space-y-1">
        {/* User info */}
        {user && !collapsed && (
          <div className="px-3 py-2 text-sm">
            <div className="flex items-center gap-2 text-muted-foreground">
              <UserIcon className="h-4 w-4" />
              <span className="font-medium truncate">{user.display_name || user.username}</span>
            </div>
            <div className="text-xs text-muted-foreground truncate ml-6">
              {user.email}
            </div>
          </div>
        )}

        <Link to="/settings" onClick={onNavigate}>
          <Button
            variant={location.pathname === '/settings' ? 'secondary' : 'ghost'}
            className="w-full justify-start gap-2"
          >
            <Settings className="h-4 w-4" />
            Settings
          </Button>
        </Link>

        <Button
          aria-label="Logout"
          variant="ghost"
          className="w-full justify-start gap-2"
          onClick={() => logout()}
        >
          <LogOut className="h-4 w-4" />
          Logout
        </Button>
      </div>
    </div>
    </>
  )
}
