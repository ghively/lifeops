/**
 * LifeOps Console navigation (BUILD_SPEC section 10).
 *
 * The section structure is fixed by the spec. Entries whose phase has not
 * shipped are shown dimmed with their phase number rather than hidden, so the
 * shape of the Console stays stable as phases land.
 */

import { Link, useLocation } from 'react-router-dom'
import {
  Activity,
  AlertCircle,
  Bot,
  Brain,
  Calendar,
  CheckSquare,
  Clock,
  FileText,
  Folder,
  Globe,
  Home,
  Settings,
  Settings2,
  ShieldCheck,
} from 'lucide-react'

import { cn } from '@/lib/utils'
import { ScrollArea } from '@/components/ui/scroll-area'

interface NavItem {
  label: string
  href: string
  icon: typeof Home
  /** The phase that makes this entry functional. 0 means it works now. */
  phase: number
}

interface NavSection {
  label: string | null
  items: NavItem[]
}

const SECTIONS: NavSection[] = [
  {
    label: null,
    items: [
      { label: 'Today', href: '/', icon: Home, phase: 0 },
      { label: 'Needs Attention', href: '/needs-attention', icon: AlertCircle, phase: 1 },
      { label: 'Waiting', href: '/waiting', icon: Clock, phase: 4 },
    ],
  },
  {
    label: 'Life',
    items: [
      { label: 'Tasks', href: '/tasks', icon: CheckSquare, phase: 0 },
      { label: 'Calendar', href: '/calendar', icon: Calendar, phase: 7 },
    ],
  },
  {
    label: 'World',
    items: [
      { label: 'World', href: '/world', icon: Globe, phase: 3 },
      { label: 'Knowledge', href: '/knowledge', icon: FileText, phase: 1 },
      { label: 'Files', href: '/files', icon: Folder, phase: 1 },
      { label: 'Memory', href: '/memory', icon: Brain, phase: 2 },
    ],
  },
  {
    label: 'Hermes',
    items: [
      { label: 'Hermes', href: '/hermes', icon: Bot, phase: 1 },
      { label: 'Activity', href: '/activity', icon: Activity, phase: 1 },
    ],
  },
  {
    label: 'System',
    items: [
      { label: 'Configuration', href: '/configuration', icon: Settings2, phase: 0 },
      { label: 'System', href: '/system', icon: Settings, phase: 0 },
    ],
  },
]

function isActive(pathname: string, href: string): boolean {
  return href === '/' ? pathname === '/' : pathname.startsWith(href)
}

export function LifeOpsSidebar({
  collapsed = false,
  onNavigate,
}: {
  collapsed?: boolean
  onNavigate?: () => void
}) {
  const { pathname } = useLocation()

  return (
    <nav
      className={cn(
        'flex h-full flex-col border-r border-border/60 bg-card',
        collapsed ? 'w-16' : 'w-60',
      )}
      aria-label="LifeOps navigation"
    >
      <div className="flex h-14 items-center gap-2 border-b border-border/60 px-4">
        <ShieldCheck className="h-5 w-5 shrink-0" />
        {!collapsed && (
          <span className="font-semibold tracking-tight">LifeOps</span>
        )}
      </div>

      <ScrollArea className="flex-1">
        <div className="space-y-5 py-4">
          {SECTIONS.map((section, index) => (
            <div key={section.label ?? `section-${index}`} className="space-y-1 px-2">
              {section.label && !collapsed && (
                <p className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                  {section.label}
                </p>
              )}
              {section.items.map((item) => {
                const active = isActive(pathname, item.href)
                const pending = item.phase > 0
                const Icon = item.icon
                return (
                  <Link
                    key={item.href}
                    to={item.href}
                    onClick={onNavigate}
                    title={
                      pending
                        ? `${item.label} — arrives in phase ${item.phase}`
                        : item.label
                    }
                    className={cn(
                      'flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm transition-colors',
                      active
                        ? 'bg-muted font-medium text-foreground'
                        : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground',
                      pending && !active && 'opacity-50',
                    )}
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    {!collapsed && <span className="flex-1 truncate">{item.label}</span>}
                    {!collapsed && pending && (
                      <span className="text-[10px] tabular-nums text-muted-foreground">
                        P{item.phase}
                      </span>
                    )}
                  </Link>
                )
              })}
            </div>
          ))}
        </div>
      </ScrollArea>

      {!collapsed && (
        <div className="border-t border-border/60 px-4 py-3 text-[11px] text-muted-foreground">
          Phase 0 · NornicDB spine
        </div>
      )}
    </nav>
  )
}
