/**
 * PresenceIndicator — Shows avatars of users currently editing the same document.
 * Displays as floating avatar bubbles (bottom-right of the editor area).
 */
import { useMemo } from 'react'
import { useCollaborationStore } from '@/stores/collaboration'
import type { PresenceUser } from '@/services/collaboration'
import { cn } from '@/lib/utils'

interface PresenceIndicatorProps {
  /** Optional className for the container */
  className?: string
  /** Max avatars to show before "+N" */
  maxVisible?: number
}

function UserAvatar({ user, size = 'md' }: { user: PresenceUser; size?: 'sm' | 'md' }) {
  const sizeClass = size === 'sm' ? 'h-7 w-7 text-xs' : 'h-9 w-9 text-sm'
  const initials = user.display_name
    .split(' ')
    .map((w) => w[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()

  return (
    <div
      className={cn(
        'flex items-center justify-center rounded-full font-semibold text-white shadow-md ring-2 ring-white transition-transform hover:scale-110 hover:z-10 cursor-default select-none',
        sizeClass,
      )}
      style={{ backgroundColor: user.color }}
      title={`${user.display_name} — editing`}
    >
      {initials}
    </div>
  )
}

export function PresenceIndicator({ className, maxVisible = 4 }: PresenceIndicatorProps) {
  const users = useCollaborationStore((s) => s.users)
  const myColor = useCollaborationStore((s) => s.myColor)
  const status = useCollaborationStore((s) => s.status)

  const { visibleUsers, overflowCount } = useMemo(() => {
    const others = users
    return {
      visibleUsers: others.slice(0, maxVisible),
      overflowCount: Math.max(0, others.length - maxVisible),
    }
  }, [users, maxVisible])

  if (status !== 'connected' || users.length === 0) {
    // Show just the current user indicator when connected
    if (status === 'connected') {
      return (
        <div className={cn('flex items-center gap-2', className)}>
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-green-500" />
            </span>
            You
          </div>
        </div>
      )
    }
    return null
  }

  return (
    <div className={cn('flex items-center gap-2', className)}>
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-75" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-green-500" />
        </span>
        {users.length === 1 ? '1 other editing' : `${users.length} others editing`}
      </div>
      <div className="flex -space-x-2">
        {visibleUsers.map((user) => (
          <UserAvatar key={user.user_id} user={user} size="sm" />
        ))}
        {overflowCount > 0 && (
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-muted text-xs font-medium ring-2 ring-white">
            +{overflowCount}
          </div>
        )}
      </div>
    </div>
  )
}

export default PresenceIndicator
