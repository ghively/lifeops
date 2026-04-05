/**
 * CollaborationService — Client-side Yjs-inspired CRDT sync over WebSocket.
 *
 * Provides real-time collaborative editing via the Knowledge OS collaboration
 * WebSocket protocol. Handles join/leave, operation broadcast, cursor sync,
 * and presence tracking.
 */

// ---------------------------------------------------------------------------
// Wire-protocol message types (must match backend)
// ---------------------------------------------------------------------------
const MSG_JOIN = 'collab.join'
const MSG_LEAVE = 'collab.leave'
const MSG_OP = 'collab.op'
const MSG_CURSOR = 'collab.cursor'
const MSG_AWARENESS = 'collab.awareness'
const MSG_SNAPSHOT_REQ = 'collab.snapshot_req'

const MSG_WELCOME = 'collab.welcome'
const MSG_USER_JOINED = 'collab.user_joined'
const MSG_USER_LEFT = 'collab.user_left'
const MSG_OP_BROADCAST = 'collab.op_broadcast'
const MSG_CURSOR_BROADCAST = 'collab.cursor_broadcast'
const MSG_AWARENESS_BROADCAST = 'collab.awareness_broadcast'
const MSG_SNAPSHOT = 'collab.snapshot'
const MSG_ACK = 'collab.ack'
const MSG_ERROR = 'collab.error'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
export interface PresenceUser {
  user_id: string
  display_name: string
  color: string
  cursor?: CursorData | null
  selection?: SelectionData | null
}

export interface CursorData {
  path: number[]
  offset: number
}

export interface SelectionData {
  anchor: { path: number[]; offset: number }
  focus: { path: number[]; offset: number }
}

export interface RemoteOperation {
  op_id: string
  object_id: string
  block_id: string
  type: string // "insert" | "delete" | "replace" | "update_props"
  path: number[]
  offset: number
  content: string
  length: number
  lamport_ts: number
  user_id: string
}

export type CollaborationStatus = 'disconnected' | 'connecting' | 'connected' | 'error'

export interface CollaborationCallbacks {
  onWelcome?: (data: { color: string; users: PresenceUser[]; pending_ops: RemoteOperation[] }) => void
  onUserJoined?: (user: PresenceUser) => void
  onUserLeft?: (user_id: string) => void
  onRemoteOp?: (op: RemoteOperation) => void
  onCursorUpdate?: (user_id: string, cursor: CursorData | null, selection: SelectionData | null) => void
  onAwarenessUpdate?: (user_id: string, state: Record<string, unknown>) => void
  onStatusChange?: (status: CollaborationStatus) => void
  onError?: (message: string) => void
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function buildWsUrl(objectId: string): string {
  const configuredApiUrl = import.meta.env.VITE_API_URL as string | undefined
  let baseUrl: string
  if (configuredApiUrl) {
    baseUrl = `${configuredApiUrl.replace(/^http/, 'ws')}`
  } else if (typeof window !== 'undefined') {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    baseUrl = `${protocol}//${window.location.host}`
  } else {
    baseUrl = ''
  }

  // Append auth token as query param (WebSocket can't send custom headers in browsers)
  const token = typeof localStorage !== 'undefined' ? localStorage.getItem('access_token') : null
  const wsPath = `/api/v1/collaboration/ws/${objectId}`
  return token ? `${baseUrl}${wsPath}?token=${encodeURIComponent(token)}` : `${baseUrl}${wsPath}`
}

// ---------------------------------------------------------------------------
// CollaborationService
// ---------------------------------------------------------------------------
export class CollaborationService {
  private ws: WebSocket | null = null
  private objectId: string | null = null
  private userId: string | null = null
  private displayName: string = 'Anonymous'
  private callbacks: CollaborationCallbacks = {}
  private reconnectAttempts = 0
  private maxReconnectAttempts = 5
  private reconnectDelay = 3000
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private manualClose = false
  private _status: CollaborationStatus = 'disconnected'
  private opQueue: RemoteOperation[] = [] // buffer for offline

  // --- Public state getters ---

  get status(): CollaborationStatus {
    return this._status
  }

  get connectedUsers(): PresenceUser[] {
    return this._users
  }

  private _users: PresenceUser[] = []
  private _myColor: string = '#e06c75'

  get myColor(): string {
    return this._myColor
  }

  // --- Connection lifecycle ---

  connect(objectId: string, userId: string, displayName: string, callbacks: CollaborationCallbacks = {}): void {
    this.disconnect()
    this.objectId = objectId
    this.userId = userId
    this.displayName = displayName
    this.callbacks = callbacks
    this.manualClose = false
    this.reconnectAttempts = 0
    this._connect()
  }

  disconnect(): void {
    this.manualClose = true
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    if (this.ws) {
      // Send leave message
      try {
        this.send({ type: MSG_LEAVE, data: {} })
      } catch {
        // ignore
      }
      this.ws.close()
      this.ws = null
    }
    this._setStatus('disconnected')
    this._users = []
  }

  // --- Sending operations ---

  /** Send a local edit operation to the server. */
  sendOp(op: Omit<RemoteOperation, 'object_id' | 'lamport_ts' | 'user_id'>): void {
    const msg = { type: MSG_OP, data: op }
    if (!this.send(msg)) {
      // Buffer for later (offline support)
      this.opQueue.push({ ...op, object_id: this.objectId ?? '', lamport_ts: 0, user_id: this.userId ?? '' })
    }
  }

  /** Send cursor position update. */
  sendCursor(cursor: CursorData | null, selection: SelectionData | null): void {
    this.send({ type: MSG_CURSOR, data: { cursor, selection } })
  }

  /** Send awareness state (e.g., typing, selection change). */
  sendAwareness(state: Record<string, unknown>): void {
    this.send({ type: MSG_AWARENESS, data: state })
  }

  /** Request a room snapshot from the server. */
  requestSnapshot(): void {
    this.send({ type: MSG_SNAPSHOT_REQ, data: {} })
  }

  // --- Internal ---

  private _connect(): void {
    if (!this.objectId) return
    this._setStatus('connecting')

    const url = buildWsUrl(this.objectId)
    const ws = new WebSocket(url)
    this.ws = ws

    ws.onopen = () => {
      // Send join message
      ws.send(JSON.stringify({
        type: MSG_JOIN,
        data: {
          user_id: this.userId,
          display_name: this.displayName,
        },
      }))

      // Flush queued ops
      while (this.opQueue.length > 0) {
        const op = this.opQueue.shift()!
        this.send({ type: MSG_OP, data: op })
      }
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        this._handleMessage(msg)
      } catch (e) {
        console.error('[CollaborationService] Failed to parse message:', e)
      }
    }

    ws.onclose = () => {
      this._setStatus('disconnected')
      if (!this.manualClose && this.reconnectAttempts < this.maxReconnectAttempts) {
        this.reconnectAttempts++
        this.reconnectTimer = setTimeout(() => this._connect(), this.reconnectDelay)
      }
    }

    ws.onerror = () => {
      this._setStatus('error')
      this.callbacks.onError?.('WebSocket connection error')
    }
  }

  private _handleMessage(msg: { type: string; data: Record<string, unknown> }): void {
    switch (msg.type) {
      case MSG_WELCOME: {
        const d = msg.data as { color: string; users: PresenceUser[]; pending_ops: RemoteOperation[]; user_id: string }
        this._myColor = d.color
        this._users = d.users || []
        this._setStatus('connected')
        this.callbacks.onWelcome?.({ color: d.color, users: d.users || [], pending_ops: d.pending_ops || [] })
        break
      }
      case MSG_USER_JOINED: {
        const user = msg.data as unknown as PresenceUser
        this._users = this._users.filter((u) => u.user_id !== user.user_id)
        this._users.push(user)
        this.callbacks.onUserJoined?.(user)
        break
      }
      case MSG_USER_LEFT: {
        const uid = (msg.data as { user_id: string }).user_id
        this._users = this._users.filter((u) => u.user_id !== uid)
        this.callbacks.onUserLeft?.(uid)
        break
      }
      case MSG_OP_BROADCAST: {
        const op = msg.data as unknown as RemoteOperation
        this.callbacks.onRemoteOp?.(op)
        break
      }
      case MSG_CURSOR_BROADCAST: {
        const d = msg.data as { user_id: string; cursor: CursorData | null; selection: SelectionData | null }
        // Update local user list
        const u = this._users.find((u) => u.user_id === d.user_id)
        if (u) {
          u.cursor = d.cursor
          u.selection = d.selection
        }
        this.callbacks.onCursorUpdate?.(d.user_id, d.cursor ?? null, d.selection ?? null)
        break
      }
      case MSG_AWARENESS_BROADCAST: {
        const d = msg.data as { user_id: string; state: Record<string, unknown> }
        this.callbacks.onAwarenessUpdate?.(d.user_id, d.state)
        break
      }
      case MSG_ACK: {
        // Operation acknowledged — could be used for optimistic UI rollback
        break
      }
      case MSG_SNAPSHOT: {
        // Snapshot response
        break
      }
      case MSG_ERROR: {
        const message = (msg.data as { message: string }).message || 'Unknown error'
        console.error('[CollaborationService] Server error:', message)
        this.callbacks.onError?.(message)
        break
      }
    }
  }

  private send(data: unknown): boolean {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data))
      return true
    }
    return false
  }

  private _setStatus(status: CollaborationStatus): void {
    this._status = status
    this.callbacks.onStatusChange?.(status)
  }
}

// Singleton for the app
export const collaborationService = new CollaborationService()
