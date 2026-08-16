/**
 * Tests for the collaboration Zustand store.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useCollaborationStore } from '../collaboration'
import type { PresenceUser } from '@/services/collaboration'

// Mock the collaboration service. Hoisted so mocks exist before vi.mock is applied.
const { mockConnect, mockDisconnect, mockSendOp, mockSendCursor, mockSendAwareness } = vi.hoisted(() => ({
  mockConnect: vi.fn(),
  mockDisconnect: vi.fn(),
  mockSendOp: vi.fn(),
  mockSendCursor: vi.fn(),
  mockSendAwareness: vi.fn(),
}))

vi.mock('@/services/collaboration', () => ({
  collaborationService: {
    connect: mockConnect,
    disconnect: mockDisconnect,
    sendOp: mockSendOp,
    sendCursor: mockSendCursor,
    sendAwareness: mockSendAwareness,
  },
  // Re-export types
  get PresenceUser() { return undefined },
}))

describe('useCollaborationStore', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Reset the store
    useCollaborationStore.setState({
      status: 'disconnected',
      users: [],
      myColor: '#e06c75',
      activeObjectId: null,
    })
  })

  it('initializes with disconnected status', () => {
    const state = useCollaborationStore.getState()
    expect(state.status).toBe('disconnected')
    expect(state.users).toEqual([])
    expect(state.activeObjectId).toBeNull()
  })

  it('connect sets activeObjectId and status to connecting', () => {
    const { connect } = useCollaborationStore.getState()
    connect('doc-1', 'user-1', 'Alice')

    const state = useCollaborationStore.getState()
    expect(state.activeObjectId).toBe('doc-1')
    expect(state.status).toBe('connecting')
    expect(mockConnect).toHaveBeenCalledWith('doc-1', 'user-1', 'Alice', expect.any(Object))
  })

  it('disconnect resets state', () => {
    const { connect, disconnect } = useCollaborationStore.getState()
    connect('doc-1', 'user-1', 'Alice')
    disconnect()

    const state = useCollaborationStore.getState()
    expect(state.status).toBe('disconnected')
    expect(state.users).toEqual([])
    expect(state.activeObjectId).toBeNull()
    expect(mockDisconnect).toHaveBeenCalled()
  })

  it('sendOp delegates to collaborationService', () => {
    const { sendOp } = useCollaborationStore.getState()
    sendOp({
      op_id: 'op-1',
      block_id: 'blk-1',
      type: 'replace',
      path: [0, 0],
      offset: 0,
      content: 'hello',
      length: 0,
    })

    expect(mockSendOp).toHaveBeenCalledWith(
      expect.objectContaining({ op_id: 'op-1', block_id: 'blk-1' }),
    )
  })

  it('sendCursor delegates to collaborationService', () => {
    const { sendCursor } = useCollaborationStore.getState()
    const cursor = { path: [0, 0], offset: 5 }
    const selection = {
      anchor: { path: [0, 0], offset: 3 },
      focus: { path: [0, 0], offset: 8 },
    }
    sendCursor(cursor, selection)

    expect(mockSendCursor).toHaveBeenCalledWith(cursor, selection)
  })

  it('callbacks update users on welcome', () => {
    // Get the callbacks passed to collaborationService.connect
    const { connect } = useCollaborationStore.getState()
    connect('doc-1', 'user-1', 'Alice')

    const callbacks = mockConnect.mock.calls[0][3]
    const mockUsers: PresenceUser[] = [
      { user_id: 'bob', display_name: 'Bob', color: '#98c379' },
      { user_id: 'carol', display_name: 'Carol', color: '#e5c07b' },
    ]

    // Simulate welcome callback
    callbacks.onWelcome({ color: '#e06c75', users: mockUsers, pending_ops: [] })

    const state = useCollaborationStore.getState()
    expect(state.status).toBe('connected')
    expect(state.myColor).toBe('#e06c75')
    expect(state.users).toEqual(mockUsers)
  })

  it('callbacks add user on user_joined', () => {
    const { connect } = useCollaborationStore.getState()
    connect('doc-1', 'user-1', 'Alice')
    const callbacks = mockConnect.mock.calls[0][3]

    // Welcome first
    callbacks.onWelcome({ color: '#e06c75', users: [], pending_ops: [] })

    // New user joins
    callbacks.onUserJoined({ user_id: 'bob', display_name: 'Bob', color: '#98c379' })

    const state = useCollaborationStore.getState()
    expect(state.users).toHaveLength(1)
    expect(state.users[0].user_id).toBe('bob')
  })

  it('callbacks remove user on user_left', () => {
    const { connect } = useCollaborationStore.getState()
    connect('doc-1', 'user-1', 'Alice')
    const callbacks = mockConnect.mock.calls[0][3]

    // Welcome with 2 users
    callbacks.onWelcome({
      color: '#e06c75',
      users: [
        { user_id: 'bob', display_name: 'Bob', color: '#98c379' },
        { user_id: 'carol', display_name: 'Carol', color: '#e5c07b' },
      ],
      pending_ops: [],
    })

    // One leaves
    callbacks.onUserLeft('bob')

    const state = useCollaborationStore.getState()
    expect(state.users).toHaveLength(1)
    expect(state.users[0].user_id).toBe('carol')
  })

  it('callbacks update user cursor on cursor_update', () => {
    const { connect } = useCollaborationStore.getState()
    connect('doc-1', 'user-1', 'Alice')
    const callbacks = mockConnect.mock.calls[0][3]

    callbacks.onWelcome({
      color: '#e06c75',
      users: [{ user_id: 'bob', display_name: 'Bob', color: '#98c379' }],
      pending_ops: [],
    })

    const cursor = { path: [0, 0], offset: 5 }
    callbacks.onCursorUpdate('bob', cursor, null)

    const state = useCollaborationStore.getState()
    expect(state.users[0].cursor).toEqual(cursor)
  })
})
