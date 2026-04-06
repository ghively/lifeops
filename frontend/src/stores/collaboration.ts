import { useEffect } from 'react'
import { create } from 'zustand'
import {
  collaborationService,
  type PresenceUser,
  type CollaborationStatus,
  type CursorData,
  type SelectionData,
  type RemoteOperation,
} from '@/services/collaboration'

/**
 * Hook that automatically disconnects from the collaboration service on unmount.
 * Call this in any component that uses the collaboration store.
 */
export function useCollaborationCleanup() {
  const disconnect = useCollaborationStore((s) => s.disconnect)
  const activeObjectId = useCollaborationStore((s) => s.activeObjectId)

  useEffect(() => {
    return () => {
      if (activeObjectId) {
        disconnect()
      }
    }
  }, [activeObjectId, disconnect])
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
export interface CollaborationState {
  /** Current connection status */
  status: CollaborationStatus
  /** Users currently in the same document */
  users: PresenceUser[]
  /** Current user's assigned color */
  myColor: string
  /** The object_id we're currently connected to (null = not connected) */
  activeObjectId: string | null

  // Actions
  connect: (objectId: string, userId: string, displayName: string) => void
  disconnect: () => void
  sendOp: (op: Omit<RemoteOperation, 'object_id' | 'lamport_ts' | 'user_id'>) => void
  sendCursor: (cursor: CursorData | null, selection: SelectionData | null) => void
  sendAwareness: (state: Record<string, unknown>) => void
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------
export const useCollaborationStore = create<CollaborationState>((set, get) => ({
  status: 'disconnected',
  users: [],
  myColor: '#e06c75',
  activeObjectId: null,

  connect: (objectId, userId, displayName) => {
    set({ activeObjectId: objectId, status: 'connecting', users: [] })

    collaborationService.connect(objectId, userId, displayName, {
      onWelcome: ({ color, users }) => {
        set({ myColor: color, users, status: 'connected' })
      },
      onUserJoined: (user) => {
        set((state) => ({
          users: [...state.users.filter((u) => u.user_id !== user.user_id), user],
        }))
      },
      onUserLeft: (user_id) => {
        set((state) => ({
          users: state.users.filter((u) => u.user_id !== user_id),
        }))
      },
      onRemoteOp: (_op) => {
        // Remote operations are handled by the editor hook, not the store
      },
      onCursorUpdate: (user_id, cursor, selection) => {
        set((state) => ({
          users: state.users.map((u) =>
            u.user_id === user_id ? { ...u, cursor: cursor ?? undefined, selection: selection ?? undefined } : u
          ),
        }))
      },
      onAwarenessUpdate: () => {
        // Could be used for typing indicators etc.
      },
      onStatusChange: (status) => {
        set({ status })
      },
      onError: (message) => {
        console.error('[CollaborationStore] Error:', message)
      },
    })
  },

  disconnect: () => {
    collaborationService.disconnect()
    set({ status: 'disconnected', users: [], activeObjectId: null })
  },

  sendOp: (op) => {
    collaborationService.sendOp(op)
  },

  sendCursor: (cursor, selection) => {
    collaborationService.sendCursor(cursor, selection)
  },

  sendAwareness: (state) => {
    collaborationService.sendAwareness(state)
  },
}))
