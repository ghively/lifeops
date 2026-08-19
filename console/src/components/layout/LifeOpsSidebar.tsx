/**
 * LifeOps Console navigation (BUILD_SPEC section 10).
 *
 * The section structure is fixed by the spec. Every entry is live: all
 * eleven phases shipped, so the phase-gating this component once carried
 * (dimmed entries with a phase badge) is gone — it was still telling users
 * that working screens had not arrived (2026-08-18 audit).
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
  Receipt,
  Repeat,
  Search,
  Send,
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
}

interface NavSection {
  label: string | null
  items: NavItem[]
}

const SECTIONS: NavSection[] = [
  {
    label: null,
    items: [
      { label: 'Today', href: '/', icon: Home },
      { label: 'Needs Attention', href: '/needs-attention', icon: AlertCircle },
      { label: 'Approvals', href: '/approvals', icon: ShieldCheck },
      { label: 'Actions', href: '/actions', icon: Send },
      { label: 'Waiting', href: '/waiting', icon: Clock },
      { label: 'Search', href: '/search', icon: Search },
    ],
  },
  {
    label: 'Life',
    items: [
      { label: 'Tasks', href: '/tasks', icon: CheckSquare },
      { label: 'Bills', href: '/bills', icon: Receipt },
      { label: 'Calendar', href: '/calendar', icon: Calendar },
    ],
  },
  {
    label: 'World',
    items: [
      { label: 'World', href: '/world', icon: Globe },
      { label: 'Knowledge', href: '/knowledge', icon: FileText },
      { label: 'Files', href: '/files', icon: Folder },
      { label: 'Memory', href: '/memory', icon: Brain },
    ],
  },
  {
    label: 'Hermes',
    items: [
      { label: 'Hermes', href: '/hermes', icon: Bot },
      { label: 'Routines', href: '/routines', icon: Repeat },
      { label: 'Activity', href: '/activity', icon: Activity },
    ],
  },
  {
    label: 'System',
    items: [
      { label: 'Configuration', href: '/configuration', icon: Settings2 },
      { label: 'System', href: '/system', icon: Settings },
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
                const Icon = item.icon
                return (
                  <Link
                    key={item.href}
                    to={item.href}
                    onClick={onNavigate}
                    title={item.label}
                    className={cn(
                      'flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm transition-colors',
                      active
                        ? 'bg-muted font-medium text-foreground'
                        : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground',
                    )}
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    {!collapsed && <span className="flex-1 truncate">{item.label}</span>}
                  </Link>
                )
              })}
            </div>
          ))}
        </div>
      </ScrollArea>

      {!collapsed && (
        <div className="border-t border-border/60 px-4 py-3 text-[11px] text-muted-foreground">
          All phases complete
        </div>
      )}
    </nav>
  )
}
