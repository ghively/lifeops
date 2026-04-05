import { useEffect, useState } from 'react'
import { PanelLeft, Search, Settings, Bell, Download } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Sidebar } from './Sidebar'
import { Button } from '@/components/ui/button'
import { AgentChatPanel } from '@/components/agents/AgentChatPanel'
import { useNavigate } from 'react-router-dom'
import { type AgentItem } from '@/services/api'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { useInstallPrompt } from '@/hooks/useInstallPrompt'
import { useAgentNotifications } from '@/hooks/useAgentNotifications'
import { useAuthStore } from '@/stores/auth'

interface MainLayoutProps {
  children: React.ReactNode
}

export function MainLayout({ children }: MainLayoutProps) {
  const { isAuthenticated } = useAuthStore()
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)
  const [selectedAgent, setSelectedAgent] = useState<AgentItem | null>(null)
  const [chatOpen, setChatOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const isMobile = useMediaQuery('(max-width: 1023px)')
  const { canInstall, install } = useInstallPrompt()
  const navigate = useNavigate()
  useAgentNotifications(isAuthenticated)

  useEffect(() => {
    if (!isMobile) {
      setMobileSidebarOpen(false)
    }
  }, [isMobile])

  const handleAgentClick = (agent: AgentItem) => {
    setSelectedAgent(agent)
    setChatOpen(true)
    setMobileSidebarOpen(false)
  }

  const handleCloseChat = () => {
    setChatOpen(false)
    setSelectedAgent(null)
  }

  const handleSearch = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && searchQuery.trim()) {
      navigate(`/search?q=${encodeURIComponent(searchQuery)}`)
    }
  }

  const [notifStatus, setNotifStatus] = useState<string | null>(null)

  const handleNotificationsClick = async () => {
    if (!('Notification' in window)) {
      setNotifStatus('unsupported')
      setTimeout(() => setNotifStatus(null), 3000)
      return
    }

    if (Notification.permission === 'default') {
      const result = await Notification.requestPermission()
      setNotifStatus(result === 'granted' ? 'enabled' : 'denied')
      setTimeout(() => setNotifStatus(null), 3000)
    } else if (Notification.permission === 'granted') {
      setNotifStatus('already')
      setTimeout(() => setNotifStatus(null), 3000)
    } else {
      setNotifStatus('blocked')
      setTimeout(() => setNotifStatus(null), 3000)
    }
  }

  return (
    <div className="flex min-h-screen bg-background">
      {/* Sidebar */}
      <Sidebar 
        collapsed={isMobile ? false : sidebarCollapsed}
        isMobile={isMobile}
        mobileOpen={mobileSidebarOpen}
        onToggle={() => {
          if (isMobile) {
            setMobileSidebarOpen(false)
            return
          }
          setSidebarCollapsed(!sidebarCollapsed)
        }}
        onAgentClick={handleAgentClick}
        onNavigate={() => setMobileSidebarOpen(false)}
      />

      {/* Main Content */}
      <div className={cn(
        'flex min-h-screen flex-1 min-w-0 flex-col transition-all duration-300',
        chatOpen && !isMobile && 'xl:mr-96'
      )}>
        {/* Header */}
        <header className="sticky top-0 z-30 border-b bg-card/95 px-4 py-3 backdrop-blur supports-[backdrop-filter]:bg-card/85">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2 min-w-0">
            <Button
              aria-label="Toggle sidebar"
              data-testid="header-sidebar-toggle"
              variant="ghost"
              size="icon"
              onClick={() => {
                if (isMobile) {
                  setMobileSidebarOpen((open) => !open)
                  return
                }
                setSidebarCollapsed(!sidebarCollapsed)
              }}
              className="shrink-0 lg:hidden"
            >
              <PanelLeft className="h-5 w-5" />
            </Button>
            
            {/* Search */}
            <div className="relative min-w-0 flex-1 sm:max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <input
                type="text"
                placeholder="Search... (Ctrl+K)"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={handleSearch}
                className="h-10 w-full rounded-md bg-muted pl-9 pr-4 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
          </div>

            <div className="flex items-center justify-end gap-2">
            {canInstall && (
              <Button aria-label="Install app" variant="outline" size="sm" onClick={() => void install()}>
                <Download className="mr-2 h-4 w-4" />
                Install
              </Button>
            )}
            <Button aria-label="Notifications" variant="ghost" size="icon" className="relative" onClick={() => void handleNotificationsClick()}>
              <Bell className="h-5 w-5" />
              {notifStatus === 'enabled' || notifStatus === 'already' ? (
                <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-green-500" />
              ) : typeof Notification !== 'undefined' && Notification.permission !== 'granted' ? (
                <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-red-500" />
              ) : null}
            </Button>
            <Button aria-label="Settings" variant="ghost" size="icon" onClick={() => navigate('/settings')}>
              <Settings className="h-5 w-5" />
            </Button>
          </div>
          </div>
        </header>

        {/* Content Area */}
        <main className="flex-1 overflow-auto">
          {children}
        </main>
      </div>

      {/* Agent Chat Panel */}
      <AgentChatPanel
        agent={selectedAgent}
        isOpen={chatOpen}
        onClose={handleCloseChat}
      />
    </div>
  )
}
