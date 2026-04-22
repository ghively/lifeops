import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { CollaborativeCursors, useCollaborativeCursors, CursorLabel, useCursorBroadcast, broadcastSelection } from '../CollaborativeCursors'
import { useCollaborationStore } from '@/stores/collaboration'
import type { PresenceUser } from '@/services/collaboration'

vi.mock('@/stores/collaboration', () => ({
  useCollaborationStore: vi.fn(),
}))

const mockCollaborationStore = useCollaborationStore as any

describe('CollaborativeCursors', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('useCollaborativeCursors', () => {
    it('filters users with cursor or selection', () => {
      const users: PresenceUser[] = [
        {
          user_id: 'user-1',
          display_name: 'Alice',
          color: '#FF0000',
          cursor: { path: [0], offset: 5 },
        },
        {
          user_id: 'user-2',
          display_name: 'Bob',
          color: '#00FF00',
          cursor: null,
        },
      ]

      mockCollaborationStore.mockReturnValue(users)

      const result = useCollaborativeCursors({} as any, 'doc-1')

      expect(result.cursorUsers).toHaveLength(1)
      expect(result.cursorUsers[0].user_id).toBe('user-1')
    })

    it('generates decorate function that returns decorations', () => {
      const users: PresenceUser[] = [
        {
          user_id: 'user-1',
          display_name: 'Alice',
          color: '#FF0000',
          cursor: { path: [0], offset: 5 },
          selection: null,
        },
      ]

      mockCollaborationStore.mockReturnValue(users)

      const mockEditor = {}
      const { decorate } = useCollaborativeCursors(mockEditor as any, 'doc-1')

      const nodeEntry = [{ text: 'hello world' }, [0]] as any

      const decorations = decorate(nodeEntry)

      expect(Array.isArray(decorations)).toBe(true)
    })

    it('handles empty cursor users list', () => {
      mockCollaborationStore.mockReturnValue([])

      const mockEditor = {}
      const { decorate } = useCollaborativeCursors(mockEditor as any, 'doc-1')

      const nodeEntry = [{ text: 'hello world' }, [0]] as any
      const decorations = decorate(nodeEntry)

      expect(decorations).toEqual([])
    })

    it('includes selection decorations when user has selection', () => {
      const users: PresenceUser[] = [
        {
          user_id: 'user-1',
          display_name: 'Alice',
          color: '#FF0000',
          cursor: null,
          selection: {
            anchor: { path: [0], offset: 2 },
            focus: { path: [0], offset: 8 },
          },
        },
      ]

      mockCollaborationStore.mockReturnValue(users)

      const mockEditor = {}
      const { decorate } = useCollaborativeCursors(mockEditor as any, 'doc-1')

      const nodeEntry = [{ text: 'hello world' }, [0]] as any
      const decorations = decorate(nodeEntry)

      expect(decorations.some((d) => d.isSelection)).toBe(true)
    })

    it('excludes undefined objectId', () => {
      const users: PresenceUser[] = [
        {
          user_id: 'user-1',
          display_name: 'Alice',
          color: '#FF0000',
          cursor: { path: [0], offset: 5 },
        },
      ]

      mockCollaborationStore.mockReturnValue(users)

      const mockEditor = {}
      const { cursorUsers } = useCollaborativeCursors(mockEditor as any, undefined)

      // Should still filter users
      expect(cursorUsers).toBeDefined()
    })
  })

  describe('CursorLabel', () => {
    it('renders user name', () => {
      render(<CursorLabel color="#FF0000" name="Alice" />)

      expect(screen.getByText('Alice')).toBeInTheDocument()
    })

    it('applies background color', () => {
      const { container } = render(<CursorLabel color="#FF0000" name="Alice" />)

      const span = container.querySelector('span')
      expect(span).toHaveStyle({ backgroundColor: '#FF0000' })
    })

    it('has select-none class', () => {
      const { container } = render(<CursorLabel color="#FF0000" name="Alice" />)

      const span = container.querySelector('span')
      expect(span?.className).toContain('select-none')
    })
  })

  describe('useCursorBroadcast', () => {
    it('broadcasts initial cursor on mount', () => {
      const mockSendCursor = vi.fn()
      mockCollaborationStore.mockReturnValue(mockSendCursor)

      const mockEditor = {
        selection: { anchor: { path: [0], offset: 5 }, focus: { path: [0], offset: 5 } },
      } as any

      useCursorBroadcast(mockEditor, 'doc-1')

      expect(mockSendCursor).toHaveBeenCalled()
    })

    it('does not broadcast without objectId', () => {
      const mockSendCursor = vi.fn()
      mockCollaborationStore.mockReturnValue(mockSendCursor)

      const mockEditor = {
        selection: { anchor: { path: [0], offset: 5 }, focus: { path: [0], offset: 5 } },
      } as any

      useCursorBroadcast(mockEditor, undefined)

      expect(mockSendCursor).not.toHaveBeenCalled()
    })

    it('does not broadcast without selection', () => {
      const mockSendCursor = vi.fn()
      mockCollaborationStore.mockReturnValue(mockSendCursor)

      const mockEditor = { selection: null } as any

      useCursorBroadcast(mockEditor, 'doc-1')

      expect(mockSendCursor).not.toHaveBeenCalled()
    })
  })

  describe('broadcastSelection', () => {
    it('broadcasts null when selection is null', () => {
      const mockSendCursor = vi.fn()
      const mockEditor = {} as any

      broadcastSelection(mockEditor, null, mockSendCursor)

      expect(mockSendCursor).toHaveBeenCalledWith(null, null)
    })

    it('broadcasts cursor data from collapsed selection', () => {
      const mockSendCursor = vi.fn()
      const mockEditor = {} as any
      const selection = {
        anchor: { path: [0], offset: 5 },
        focus: { path: [0], offset: 5 },
      }

      broadcastSelection(mockEditor, selection as any, mockSendCursor)

      expect(mockSendCursor).toHaveBeenCalled()
      const call = mockSendCursor.mock.calls[0]
      expect(call[0]).toEqual({ path: [0], offset: 5 })
      expect(call[1]).toBeNull() // No selection data for collapsed range
    })

    it('broadcasts cursor and selection data from range selection', () => {
      const mockSendCursor = vi.fn()
      const mockEditor = {} as any
      const selection = {
        anchor: { path: [0], offset: 2 },
        focus: { path: [0], offset: 8 },
      }

      broadcastSelection(mockEditor, selection as any, mockSendCursor)

      expect(mockSendCursor).toHaveBeenCalled()
      const call = mockSendCursor.mock.calls[0]
      expect(call[0]).toEqual({ path: [0], offset: 2 })
      expect(call[1]).toEqual({
        anchor: { path: [0], offset: 2 },
        focus: { path: [0], offset: 8 },
      })
    })
  })
})
