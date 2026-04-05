import { useState } from 'react'
import { PanelLeft, Search, Settings, Bell } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Sidebar } from './Sidebar'
import { Button } from '@/components/ui/button'
import { AgentChatPanel } from '@/components/agents/AgentChatPanel'
import { useNavigate } from 'react-router-dom'
import { type AgentItem } from '@/services/api'

interface MainLayoutProps {
  children: React.ReactNode
}

export function MainLayout({ children }: MainLayoutProps) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [selectedAgent, setSelectedAgent] = useState<AgentItem | null>(null)
  const [chatOpen, setChatOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const navigate = useNavigate()

  const handleAgentClick = (agent: AgentItem) => {
    setSelectedAgent(agent)
    setChatOpen(true)
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

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <Sidebar 
        collapsed={sidebarCollapsed} 
        onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
        onAgentClick={handleAgentClick}
      />

      {/* Main Content */}
      <div className={cn(
        "flex-1 flex flex-col min-w-0 transition-all duration-300",
        chatOpen && "mr-96"
      )}>
        {/* Header */}
        <header className="h-14 border-b flex items-center justify-between px-4 bg-card">
          <div className="flex items-center gap-2">
            <Button
              aria-label="Toggle sidebar"
              data-testid="header-sidebar-toggle"
              variant="ghost"
              size="icon"
              onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
              className="lg:hidden"
            >
              <PanelLeft className="h-5 w-5" />
            </Button>
            
            {/* Search */}
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <input
                type="text"
                placeholder="Search... (Ctrl+K)"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={handleSearch}
                className="pl-9 pr-4 py-1.5 bg-muted rounded-md text-sm w-64 focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button aria-label="Notifications" variant="ghost" size="icon" className="relative">
              <Bell className="h-5 w-5" />
              <span className="absolute top-1 right-1 h-2 w-2 bg-red-500 rounded-full" />
            </Button>
            <Button aria-label="Settings" variant="ghost" size="icon" onClick={() => navigate('/settings')}>
              <Settings className="h-5 w-5" />
            </Button>
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
