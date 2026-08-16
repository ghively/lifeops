/**
 * LifeOps Console shell.
 *
 * Keeps the Knowledge-OS shell behaviour worth keeping — responsive sidebar,
 * theme system, mobile drawer — over the LifeOps navigation.
 */

import { useEffect, useState } from 'react'
import { PanelLeft } from 'lucide-react'

import { LifeOpsSidebar } from './LifeOpsSidebar'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { useLifeOpsEvents } from '@/lib/useLifeOpsEvents'
import { cn } from '@/lib/utils'

export function LifeOpsLayout({ children }: { children: React.ReactNode }) {
  const isMobile = useMediaQuery('(max-width: 1023px)')
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)

  // Live server events keep every mounted page's caches fresh.
  useLifeOpsEvents()

  useEffect(() => {
    if (!isMobile) setMobileOpen(false)
  }, [isMobile])

  return (
    <div className="flex h-screen overflow-hidden bg-background text-foreground">
      {!isMobile && <LifeOpsSidebar collapsed={collapsed} />}

      {isMobile && mobileOpen && (
        <>
          <button
            type="button"
            aria-label="Close navigation"
            className="fixed inset-0 z-40 bg-black/40"
            onClick={() => setMobileOpen(false)}
          />
          <div className="fixed inset-y-0 left-0 z-50">
            <LifeOpsSidebar onNavigate={() => setMobileOpen(false)} />
          </div>
        </>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border/60 px-4">
          <button
            type="button"
            aria-label="Toggle navigation"
            className={cn(
              'rounded-md p-1.5 text-muted-foreground transition-colors',
              'hover:bg-muted hover:text-foreground',
            )}
            onClick={() =>
              isMobile ? setMobileOpen((v) => !v) : setCollapsed((v) => !v)
            }
          >
            <PanelLeft className="h-4 w-4" />
          </button>
        </header>

        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  )
}
