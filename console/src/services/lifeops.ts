/**
 * LifeOps Core API client.
 *
 * This replaces the Knowledge-OS backend client for every screen that has been
 * migrated. The old `services/api.ts` remains only for screens still parked
 * pending Phase 1; nothing here depends on it.
 *
 * All state reaches NornicDB through LifeOps Core. The Console never talks to
 * the database directly (BUILD_SPEC section 3).
 */

import axios, { type AxiosInstance } from 'axios'

import { getToken, handleUnauthorized } from '@/lib/auth'

const BASE_URL: string =
  (import.meta.env.VITE_LIFEOPS_URL as string | undefined) ?? 'http://127.0.0.1:8080'

/** Base URL with the HTTP scheme swapped for its WebSocket equivalent. */
export const WS_BASE_URL: string = BASE_URL.replace(/^http/, 'ws')

export const lifeops: AxiosInstance = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
    // Identifies the Console to LifeOps policy. The server decides what this
    // identity may do; the header only declares who is asking.
    'X-LifeOps-Client': 'lifeops-console',
  },
  timeout: 30000,
  // Repeat array parameters as `types=a&types=b`. Axios defaults to
  // `types[]=a`, which FastAPI does not bind to a `list[str]` query
  // parameter — the filter would be silently ignored rather than fail.
  paramsSerializer: { indexes: null },
})

/** A LifeOps error carries a stable code the UI can branch on. */
export interface LifeOpsErrorBody {
  code: string
  message: string
  details?: Record<string, unknown>
}

export class LifeOpsError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status?: number,
    public readonly details?: Record<string, unknown>,
  ) {
    super(message)
    this.name = 'LifeOpsError'
  }
}

lifeops.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers.set('Authorization', `Bearer ${token}`)
  }
  return config
})

lifeops.interceptors.response.use(
  (response) => response,
  (error) => {
    const body = error?.response?.data as LifeOpsErrorBody | undefined
    // A 401 anywhere except the login attempt itself means the session is
    // gone: drop the token and route the whole app to the login screen. The
    // login endpoint's own 401 is a wrong password and must surface to the
    // form instead.
    const url = (error?.config?.url as string | undefined) ?? ''
    if (error?.response?.status === 401 && !url.includes('/auth/login')) {
      handleUnauthorized()
    }
    if (body?.code) {
      return Promise.reject(
        new LifeOpsError(body.code, body.message, error.response?.status, body.details),
      )
    }
    return Promise.reject(error)
  },
)

// --- domain types ------------------------------------------------------------

export type TaskState =
  | 'CAPTURED'
  | 'PLANNED'
  | 'READY'
  | 'EXECUTING'
  | 'WAITING_EXTERNAL'
  | 'NEEDS_APPROVAL'
  | 'VERIFYING'
  | 'COMPLETED'
  | 'BLOCKED'
  | 'FAILED'
  | 'CANCELLED'

export type TaskPriority = 'low' | 'medium' | 'high' | 'urgent'

export interface Task {
  id: string
  title: string
  description: string | null
  state: TaskState
  priority: TaskPriority
  created_at: string
  updated_at: string
  due_at: string | null
  owner_entity_id: string | null
  assigned_client: string | null
  current_action: string | null
  waiting_item_id: string | null
  verification_required: boolean
  verification_state: string
  verification_evidence: string | null
  related_entity_ids: string[]
  source: string | null
  created_by_client: string | null
  needs_attention: boolean
}

export interface TaskList {
  tasks: Task[]
  total: number
  by_state: Record<string, number>
}

export interface Person {
  id: string
  display_name: string
  is_primary: boolean
  aliases: string[]
  timezone: string | null
  created_at: string
  updated_at: string
}

export interface Preference {
  id: string
  subject_id: string
  key: string
  value: string
  source_type: string
  source_id: string | null
  confidence: number
  importance: number
  observed_at: string
  created_at: string
  valid_from: string
  valid_to: string | null
  supersedes: string | null
  created_by_client: string | null
  notes: string | null
  is_current: boolean
}

// --- configuration types -----------------------------------------------------

export type ProviderState =
  | 'not_configured'
  | 'configured'
  | 'healthy'
  | 'unhealthy'
  | 'disabled'

export type FieldKind = 'text' | 'secret' | 'number' | 'boolean' | 'select' | 'url'

export interface ProviderField {
  name: string
  kind: FieldKind
  label: string
  required: boolean
  description: string
  default: unknown
  placeholder: string | null
  options: Array<{ value: string; label: string }>
  options_from: string | null
  minimum: number | null
  maximum: number | null
  step: number | null
  advanced: boolean
}

export interface ProviderDefinition {
  id: string
  category: string
  display_name: string
  summary: string
  fields: ProviderField[]
  capabilities: string[]
  available_in_phase: number
  docs_url: string | null
}

export interface ProviderStatus {
  id: string
  display_name: string
  category: string
  summary: string
  state: ProviderState
  enabled: boolean
  available_in_phase: number
  settings: Record<string, unknown>
  secrets: Record<string, { configured: boolean; fingerprint: string | null }>
  missing_required: string[]
  capabilities: string[]
  last_health: {
    healthy: boolean
    checked_at: string
    message: string
    details: Record<string, unknown>
  } | null
}

export interface ProviderEntry {
  definition: ProviderDefinition
  status: ProviderStatus
}

/** BUILD_SPEC section 29 — which ASR/TTS pairing the Voice Bridge uses. */
export type VoiceMode = 'quick_cloud' | 'hybrid' | 'local'

export interface SystemConfig {
  display_name: string
  timezone: string
  household_name: string
  primary_person_id: string | null
  local_url: string | null
  setup_completed: boolean
  safe_mode: boolean
  voice_mode: VoiceMode
}

export interface ComponentHealth {
  healthy: boolean
  detail: string
}

export interface SystemStatus {
  components: Record<string, ComponentHealth | boolean>
  providers: ProviderStatus[]
  system: SystemConfig
  clients: Array<{
    client_id: string
    role: string
    display_name: string
    description: string
    capabilities: string[]
  }>
  requesting_client: {
    client_id: string
    role: string
    display_name: string
    description: string
    capabilities: string[]
  }
}

// --- auth / activity / log types ----------------------------------------------

/** Who the server believes this session is (GET /auth/me). */
export interface AuthIdentity {
  client_id: string
  display_name: string
  auth_enabled: boolean
}

/**
 * One entry in the server's ephemeral activity ring buffer
 * (BUILD_SPEC section 21): a semantic operation with its outcome.
 * Durable audit is Phase 4; this feed resets when LifeOps Core restarts.
 */
export interface ActivityEntry {
  ts: string
  operation: string
  result: string
  duration_ms: number | null
  client_id?: string
  task_id?: string
  person_id?: string
  subject_id?: string
  key?: string
}

/** A frontend log record accepted by POST /system/logs. */
export interface RemoteLogEntry {
  level: 'debug' | 'info' | 'warn' | 'error'
  message: string
  context?: Record<string, unknown>
  ts: string
}

export interface SearchResults {
  people: Person[]
  preferences: Preference[]
  tasks: Task[]
}

// --- memory types (BUILD_SPEC sections 42-47) ---------------------------------

export type MemoryType =
  | 'episodic'
  | 'semantic'
  | 'preference_candidate'
  | 'summary'
  | 'association'

/**
 * One durable memory with provenance and a validity window. A record is never
 * edited in place: correction supersedes it and invalidation closes
 * `valid_to`, so `supersedes`/`valid_to` are the history trail.
 */
export interface MemoryRecord {
  id: string
  subject_id: string
  type: MemoryType
  content: string
  source_type: string
  source_id: string | null
  observed_at: string
  created_at: string
  confidence: number
  importance: number
  valid_from: string
  valid_to: string | null
  supersedes: string | null
  entity_ids: string[]
  created_by_client: string | null
  invalidation_reason: string | null
}

export interface MemoryList {
  memories: MemoryRecord[]
  total: number
}

// --- durable work types (BUILD_SPEC sections 13, 54-62, phase 4) --------------
//
// These mirror the Core schemas one-for-one, the same discipline the world
// types follow. LifeOps Core decides everything that matters here — whether
// a follow-up escalates, whether an action needs approval, what an approval
// authorises; the Console only renders and submits.

export type WaitingStatus = 'waiting' | 'escalated' | 'resolved' | 'cancelled'

/** One WaitingItem (BUILD_SPEC section 54) — the Waiting screen's unit
 * (section 13). */
export interface WaitingItem {
  id: string
  task_id: string
  subject: string
  waiting_on_entity_id: string | null
  waiting_since: string
  expected_by: string | null
  next_action_at: string | null
  last_contact_at: string | null
  followup_count: number
  max_followups: number
  status: WaitingStatus
  attempt_count: number
  lease_owner: string | null
  lease_until: string | null
  created_by_client: string | null
}

export interface WaitingList {
  items: WaitingItem[]
  total: number
}

export type ActionType =
  | 'send_email'
  | 'request_quote'
  | 'book_appointment'
  | 'cancel_appointment'
  | 'place_phone_call'
  | 'build_grocery_cart'
  | 'submit_grocery_order'
  | 'prepare_payment'
  | 'commit_payment'

export type ActionStatus =
  | 'prepared'
  | 'needs_approval'
  | 'approved'
  | 'executing'
  | 'executed'
  | 'verified'
  | 'failed'
  | 'cancelled'

/** One outbox action (BUILD_SPEC section 60). Named `LifeOpsAction` to stay
 * unambiguous next to DOM and React "action" usages elsewhere. */
export interface LifeOpsAction {
  id: string
  type: ActionType
  status: ActionStatus
  idempotency_key: string
  payload_hash: string
  payload: Record<string, unknown>
  task_id: string | null
  target_entity_id: string | null
  created_at: string
  attempt_count: number
  last_attempt_at: string | null
  external_reference: string | null
  verification_state: string
  failure_reason: string | null
  created_by_client: string | null
}

export interface ActionList {
  actions: LifeOpsAction[]
  total: number
}

export type ApprovalStatus = 'pending' | 'approved' | 'declined' | 'expired'

/**
 * One approval (BUILD_SPEC sections 57-59), enriched for the Approval screen
 * (section 58): `action_payload` and `action_status` are the exact action
 * this approval binds to, attached by the server so the screen never has to
 * decide what "what will happen" means on its own.
 */
export interface Approval {
  id: string
  action_id: string
  payload_hash: string
  requested_by: string
  approved_by: string | null
  approved_at: string | null
  expires_at: string
  consumed_at: string | null
  status: ApprovalStatus
  action_type: string
  /** Section 58's two lists, decided by the domain, rendered verbatim here. */
  authorises_action: string
  does_not_authorise: string[]
  target_entity_id: string | null
  amount: string | null
  created_at: string
  action_payload: Record<string, unknown>
  action_status: ActionStatus | null
}

export interface ApprovalList {
  approvals: Approval[]
  total: number
}

/** One audit record (BUILD_SPEC section 62) — "why did Hermes do that?" */
export interface AuditRecord {
  id: string
  requester: string | null
  user: string | null
  client: string
  session: string | null
  intent: string | null
  tool: string | null
  risk: string | null
  approval: string | null
  action: string | null
  target: string | null
  result: string
  verification: string | null
  timestamp: string
  trace_id: string | null
  details: Record<string, string>
}

export interface AuditList {
  records: AuditRecord[]
  total: number
}

// --- API surface -------------------------------------------------------------

export const authApi = {
  login: (password: string) =>
    lifeops.post<{ token: string }>('/auth/login', { password }).then((r) => r.data),

  me: () => lifeops.get<AuthIdentity>('/auth/me').then((r) => r.data),

  /** First setup needs no current password; changes do (BUILD_SPEC §22). */
  setPassword: (newPassword: string, currentPassword?: string) =>
    lifeops
      .post<{ auth_enabled: boolean }>('/auth/password', {
        current_password: currentPassword,
        new_password: newPassword,
      })
      .then((r) => r.data),
}

export const tasksApi = {
  list: (params?: { state?: TaskState[]; limit?: number; offset?: number }) =>
    lifeops.get<TaskList>('/tasks', { params }).then((r) => r.data),

  get: (id: string) => lifeops.get<Task>(`/tasks/${id}`).then((r) => r.data),

  create: (payload: {
    title: string
    description?: string
    priority?: TaskPriority
    due_at?: string
    verification_required?: boolean
  }) => lifeops.post<Task>('/tasks', payload).then((r) => r.data),

  update: (
    id: string,
    payload: Partial<{
      title: string
      description: string
      state: TaskState
      priority: TaskPriority
      due_at: string
      current_action: string
      verification_evidence: string
    }>,
  ) => lifeops.patch<Task>(`/tasks/${id}`, payload).then((r) => r.data),
}

export const waitingApi = {
  /** The Waiting screen's list (BUILD_SPEC section 13). */
  list: (params?: { status?: WaitingStatus[]; limit?: number }) =>
    lifeops.get<WaitingList>('/waiting', { params }).then((r) => r.data),

  get: (id: string) => lifeops.get<WaitingItem>(`/waiting/${id}`).then((r) => r.data),

  /** Record that a task is blocked on someone else. Captures a fact; sends
   * nothing (BUILD_SPEC section 54). */
  create: (payload: {
    task_id: string
    subject: string
    waiting_on_entity_id?: string
    expected_by?: string
    max_followups?: number
  }) => lifeops.post<WaitingItem>('/waiting', payload).then((r) => r.data),

  /** Log a follow-up, escalating when the budget is spent (section 55). */
  followUp: (id: string) =>
    lifeops.post<WaitingItem>(`/waiting/${id}/followup`).then((r) => r.data),

  /** Close a waiting item because the thing arrived. */
  resolve: (id: string) =>
    lifeops.post<WaitingItem>(`/waiting/${id}/resolve`).then((r) => r.data),
}

export const approvalsApi = {
  /** What the Approval screen shows (BUILD_SPEC section 58). */
  listPending: (params?: { limit?: number }) =>
    lifeops.get<ApprovalList>('/approvals', { params }).then((r) => r.data),

  /**
   * Approve or decline one exact action. LifeOps Core already decided
   * whether approval was required and what it binds to; this only submits
   * the human's decision (section 58).
   */
  decide: (id: string, approved: boolean) =>
    lifeops
      .post<Approval>(`/approvals/${id}/decide`, { approved })
      .then((r) => r.data),
}

export const actionsApi = {
  list: (params?: { status?: ActionStatus[]; limit?: number }) =>
    lifeops.get<ActionList>('/actions', { params }).then((r) => r.data),

  get: (id: string) => lifeops.get<LifeOpsAction>(`/actions/${id}`).then((r) => r.data),
}

export const auditApi = {
  /** The durable audit log — "why did Hermes do that?" (section 62). */
  read: (params?: { target?: string; limit?: number }) =>
    lifeops.get<AuditList>('/audit', { params }).then((r) => r.data),
}

export const peopleApi = {
  me: () => lifeops.get<Person>('/people/me').then((r) => r.data),
  list: () =>
    lifeops.get<{ people: Person[]; total: number }>('/people').then((r) => r.data),
}

export const preferencesApi = {
  list: (params?: { subject_id?: string; key_prefix?: string }) =>
    lifeops
      .get<{ preferences: Preference[]; subject_id: string; total: number }>(
        '/preferences',
        { params },
      )
      .then((r) => r.data),

  history: (key: string) =>
    lifeops
      .get<{ key: string; history: Preference[]; total: number }>(
        '/preferences/history',
        { params: { key } },
      )
      .then((r) => r.data),

  save: (payload: { key: string; value: string; notes?: string }) =>
    lifeops.post<Preference>('/preferences', payload).then((r) => r.data),

  invalidate: (id: string) =>
    lifeops.delete<Preference>(`/preferences/${id}`).then((r) => r.data),
}

export const configApi = {
  listProviders: () =>
    lifeops
      .get<{ providers: ProviderEntry[] }>('/config/providers')
      .then((r) => r.data.providers),

  getProvider: (id: string) =>
    lifeops.get<ProviderEntry>(`/config/providers/${id}`).then((r) => r.data),

  /**
   * Send a partial configuration update. Secret fields are routed to the
   * SecretStore server-side and are never returned in the response.
   */
  updateProvider: (id: string, values: Record<string, unknown>) =>
    lifeops
      .put<{ status: ProviderStatus }>(`/config/providers/${id}`, values)
      .then((r) => r.data.status),

  testProvider: (id: string) =>
    lifeops
      .post<{
        provider: string
        healthy: boolean
        state: string
        message: string
        checked_at: string
      }>(`/config/providers/${id}/test`)
      .then((r) => r.data),

  discover: (id: string, field: string) =>
    lifeops
      .post<{ provider: string; field: string; options: Array<{ value: string; label: string }>; message: string }>(
        `/config/providers/${id}/discover`,
        null,
        { params: { field } },
      )
      .then((r) => r.data),

  getSystem: () => lifeops.get<SystemConfig>('/config/system').then((r) => r.data),

  updateSystem: (values: Partial<SystemConfig>) =>
    lifeops.put<SystemConfig>('/config/system', values).then((r) => r.data),
}

export interface SynthesizeSpeechRequest {
  text: string
  voice_id?: string
  model_id?: string
  output_format?: string
  stability?: number
  similarity_boost?: number
  speed?: number
}

/**
 * `responseType: 'blob'` makes axios hand back a Blob on an error response
 * too, so the usual `LifeOpsError` interceptor never sees the JSON body.
 * Re-parse it here so a "not configured" preview failure still surfaces the
 * server's message instead of a generic one.
 */
async function toBlobAwareError(error: unknown): Promise<unknown> {
  if (
    axios.isAxiosError(error) &&
    error.response?.data instanceof Blob &&
    error.response.data.type.includes('json')
  ) {
    try {
      const body = JSON.parse(await error.response.data.text()) as LifeOpsErrorBody
      if (body?.code) {
        return new LifeOpsError(body.code, body.message, error.response.status, body.details)
      }
    } catch {
      // Not parseable JSON after all — fall through to the original error.
    }
  }
  return error
}

export const voiceApi = {
  /**
   * Synthesize sample text and return playable audio (BUILD_SPEC section 27's
   * Preview voice button). Never saves anything and does not require Hermes.
   */
  previewVoice: async (payload: SynthesizeSpeechRequest): Promise<Blob> => {
    try {
      const response = await lifeops.post<Blob>('/voice/tts/preview', payload, {
        responseType: 'blob',
      })
      return response.data
    } catch (error) {
      throw await toBlobAwareError(error)
    }
  },
}

export const searchApi = {
  search: (q: string) =>
    lifeops.get<SearchResults>('/search', { params: { q } }).then((r) => r.data),
}

export const memoryApi = {
  /**
   * Current memories. `include_invalid: true` is refused loudly by the server
   * (422, reason `include_invalid_unsupported`) until LifeOps Core grows a
   * listing for closed records — closed versions are read per memory through
   * `history()` instead.
   */
  list: (params?: {
    subject_id?: string
    type?: MemoryType[]
    include_invalid?: boolean
    limit?: number
  }) => lifeops.get<MemoryList>('/memory', { params }).then((r) => r.data),

  get: (id: string) =>
    lifeops.get<MemoryRecord>(`/memory/${id}`).then((r) => r.data),

  search: (q: string, params?: { subject_id?: string; limit?: number }) =>
    lifeops
      .get<MemoryList>('/memory/search', { params: { q, ...params } })
      .then((r) => r.data),

  /** The supersession chain: every version of this memory, current and closed. */
  history: (id: string) =>
    lifeops
      .get<{ memory_id: string; history: MemoryRecord[]; total: number }>(
        `/memory/${id}/history`,
      )
      .then((r) => r.data),

  /** Store an observation. This records intent; it executes nothing (§44). */
  remember: (payload: {
    content: string
    type: MemoryType
    subject_id?: string
    source_type?: string
    source_id?: string
    confidence?: number
    importance?: number
    entity_ids?: string[]
  }) => lifeops.post<MemoryRecord>('/memory', payload).then((r) => r.data),

  /** Close the validity window. The record is never deleted. */
  invalidate: (id: string, reason: string) =>
    lifeops
      .post<MemoryRecord>(`/memory/${id}/invalidate`, { reason })
      .then((r) => r.data),

  /** Correction is supersession: the old record closes, a new one opens. */
  correct: (id: string, content: string) =>
    lifeops
      .post<MemoryRecord>(`/memory/${id}/correct`, { content })
      .then((r) => r.data),
}

export const systemApi = {
  status: () => lifeops.get<SystemStatus>('/system/status').then((r) => r.data),
  health: () =>
    lifeops
      .get<{ status: string; components: Record<string, ComponentHealth | boolean> }>(
        '/health',
      )
      .then((r) => r.data),

  /**
   * The state machine's transition table, served by LifeOps Core so the UI
   * offers only what the machine currently permits (SECURITY.md: the Console
   * must not mirror the table locally). Display only — the server still
   * re-validates every transition.
   */
  getTransitions: () =>
    lifeops
      .get<{ transitions: Record<TaskState, TaskState[]> }>('/tasks/transitions')
      .then((r) => r.data.transitions),

  /** Ephemeral activity ring buffer (BUILD_SPEC section 21). */
  getActivity: () =>
    lifeops
      .get<{ entries: ActivityEntry[] }>('/system/activity')
      .then((r) => r.data.entries),

  /**
   * Ship frontend logs to the server. Fire-and-forget by contract — callers
   * (the logger sink) swallow failures so logging never breaks the app.
   */
  postLogs: (entries: RemoteLogEntry[]) =>
    lifeops.post('/system/logs', { entries }).then(() => undefined),
}

// --- world types (BUILD_SPEC sections 15-16, 36-39) ---------------------------
//
// These mirror the Core schemas one-for-one. Where the API returns raw graph
// edges, the Console derives the reading direction itself (see
// `relationshipsFrom` below) rather than expecting the server to pre-chew it.

/** One node in the world graph: an entity reduced to what the graph needs. */
export interface WorldGraphNode {
  id: string
  entity_type: string
  label: string
  status: string
}

/** One directed, labelled relationship between two entities. */
export interface WorldGraphEdge {
  source: string
  target: string
  type: string
}

export interface WorldGraph {
  nodes: WorldGraphNode[]
  edges: WorldGraphEdge[]
}

/** Entity types the Console may create directly (BUILD_SPEC section 15). */
export type WorldCreatableType = 'household' | 'provider' | 'asset'

/**
 * The BUILD_SPEC section 39 relationship vocabulary, in the spec's order.
 * Mirrors the Core schema exactly, so the picker never offers a type the
 * server would reject and never hides one it accepts.
 */
export const WORLD_RELATIONSHIP_TYPES = [
  'MEMBER_OF',
  'RELATED_TO',
  'PREFERS',
  'OWNS',
  'USES_PROVIDER',
  'ASSIGNED_TO',
  'ABOUT',
  'WITH_PROVIDER',
  'FOR_ASSET',
  'WAITING_ON',
  'REQUIRES_APPROVAL',
  'AUTHORIZES',
  'CREATED_BY',
  'REQUESTED_BY',
  'EXECUTED_BY',
  'VERIFIED_BY',
  'DERIVED_FROM',
  'SUPERSEDES',
  'RELATED_MEMORY',
  'REFERENCES',
] as const

export type WorldRelationshipType = (typeof WORLD_RELATIONSHIP_TYPES)[number]

/** A world entity with its current facts. */
export interface WorldEntity {
  id: string
  entity_type: string
  display_name: string
  facts: Record<string, string>
  created_at: string
  updated_at: string
  created_by_client: string | null
}

export interface WorldEntityDetail {
  entity: WorldEntity
  relationships: WorldGraphEdge[]
  neighbors: WorldGraphNode[]
  related_tasks: Task[]
  related_memories: MemoryRecord[]
}

export interface WorldEntityHistory {
  entity_id: string
  memories: MemoryRecord[]
  /** What this history does and does not cover, stated by the server. */
  covers: string[]
}

/** One relationship read from the perspective of the inspected entity. */
export interface WorldRelationshipView {
  type: string
  direction: 'outgoing' | 'incoming'
  otherId: string
  otherLabel: string
  otherEntityType: string | null
}

/**
 * Turn raw edges into rows the inspector can render.
 *
 * The far endpoint is whichever end is not the inspected entity; its label
 * comes from `neighbors`, falling back to the id so a partially-resolved
 * graph still renders something truthful.
 */
export function relationshipsFrom(
  entityId: string,
  detail: WorldEntityDetail,
): WorldRelationshipView[] {
  const byId = new Map(detail.neighbors.map((node) => [node.id, node]))
  return detail.relationships.map((edge) => {
    const outgoing = edge.source === entityId
    const otherId = outgoing ? edge.target : edge.source
    const other = byId.get(otherId)
    return {
      type: edge.type,
      direction: outgoing ? 'outgoing' : 'incoming',
      otherId,
      otherLabel: other?.label ?? otherId,
      otherEntityType: other?.entity_type ?? null,
    }
  })
}

export const worldApi = {
  /**
   * The current world graph. `types` narrows which entity types are included
   * and `query` filters by name.
   */
  graph: (params?: { types?: string[]; query?: string; limit?: number }) =>
    lifeops
      .get<WorldGraph>('/world/graph', {
        params: {
          // Repeated `types=` parameters, not a comma-joined string: a display
          // name containing a comma must not become two filters.
          types: params?.types && params.types.length > 0 ? params.types : undefined,
          query: params?.query || undefined,
          limit: params?.limit,
        },
      })
      .then((r) => r.data),

  /** The graph around one entity, for click-to-expand. */
  neighborhood: (entityId: string, depth = 1) =>
    lifeops
      .get<WorldGraph>('/world/neighborhood', {
        params: { entity_id: entityId, depth },
      })
      .then((r) => r.data),

  /** The full inspector payload for one entity (BUILD_SPEC section 16). */
  entity: (id: string) =>
    lifeops.get<WorldEntityDetail>(`/world/entities/${id}`).then((r) => r.data),

  history: (id: string) =>
    lifeops
      .get<WorldEntityHistory>(`/world/entities/${id}/history`)
      .then((r) => r.data),

  /**
   * A domain operation, not raw editing: create a household, provider, or
   * asset with its initial facts (BUILD_SPEC section 15).
   */
  createEntity: (payload: {
    entity_type: WorldCreatableType
    display_name: string
    facts?: Record<string, string>
  }) => lifeops.post<WorldEntity>('/world/entities', payload).then((r) => r.data),

  /** Link two entities with a typed relationship. */
  link: (payload: { source_id: string; target_id: string; rel_type: string }) =>
    lifeops.post<WorldGraphEdge>('/world/relationships', payload).then((r) => r.data),

  /**
   * Remove a typed relationship. The triple travels as query parameters
   * because DELETE bodies are dropped by some proxies and HTTP clients.
   */
  unlink: (payload: { source_id: string; target_id: string; rel_type: string }) =>
    lifeops.delete('/world/relationships', { params: payload }).then(() => undefined),
}

// --- display helpers ---------------------------------------------------------

export const TASK_STATE_LABELS: Record<TaskState, string> = {
  CAPTURED: 'Captured',
  PLANNED: 'Planned',
  READY: 'Ready',
  EXECUTING: 'Executing',
  WAITING_EXTERNAL: 'Waiting',
  NEEDS_APPROVAL: 'Needs approval',
  VERIFYING: 'Verifying',
  COMPLETED: 'Completed',
  BLOCKED: 'Blocked',
  FAILED: 'Failed',
  CANCELLED: 'Cancelled',
}

/** Display names for action types (BUILD_SPEC section 51), for the Approval
 * screen's "Hermes may" line (section 58). */
export const ACTION_TYPE_LABELS: Record<ActionType, string> = {
  send_email: 'Send an email',
  request_quote: 'Request a quote',
  book_appointment: 'Book appointment',
  cancel_appointment: 'Cancel appointment',
  place_phone_call: 'Place a phone call',
  build_grocery_cart: 'Build a grocery cart',
  submit_grocery_order: 'Submit a grocery order',
  prepare_payment: 'Prepare a payment',
  commit_payment: 'Commit a payment',
}

/** Display names for the world-model entity types (BUILD_SPEC section 36). */
export const WORLD_TYPE_LABELS: Record<string, string> = {
  person: 'Person',
  household: 'Household',
  preference: 'Preference',
  task: 'Task',
  waiting_item: 'Waiting item',
  provider: 'Provider',
  appointment: 'Appointment',
  event: 'Event',
  asset: 'Asset',
  service_request: 'Service request',
  bill: 'Bill',
  shopping_list: 'Shopping list',
  action: 'Action',
  approval: 'Approval',
  memory: 'Memory',
  knowledge: 'Knowledge',
  document: 'Document',
  workflow_template: 'Workflow template',
}

export function worldTypeLabel(entityType: string): string {
  return WORLD_TYPE_LABELS[entityType] ?? entityType
}

export const MEMORY_TYPE_LABELS: Record<MemoryType, string> = {
  episodic: 'Episodic',
  semantic: 'Fact',
  preference_candidate: 'Preference candidate',
  summary: 'Summary',
  association: 'Association',
}

export const MEMORY_SOURCE_LABELS: Record<string, string> = {
  user_explicit: 'Stated by you',
  user_inferred: 'Inferred from your words',
  conversation: 'Conversation',
  email: 'Email',
  calendar: 'Calendar',
  document: 'Document',
  website: 'Website',
  phone_call: 'Phone call',
  system: 'System',
  agent: 'Assistant inference',
}

// --- display helpers ---------------------------------------------------------



/**
 * Turn any thrown value into something worth showing a human.
 *
 * A LifeOps error already carries a written explanation. A network failure
 * does not, and "Network Error" tells the user nothing actionable about a
 * local service that is simply not running.
 */
export function errorMessage(error: unknown): string {
  if (error instanceof LifeOpsError) return error.message
  if (axios.isAxiosError(error) && !error.response) {
    return `Cannot reach LifeOps Core at ${BASE_URL}. Is it running?`
  }
  if (error instanceof Error) return error.message
  return 'Something went wrong.'
}

export const PROVIDER_STATE_LABELS: Record<ProviderState, string> = {
  not_configured: 'Not configured',
  configured: 'Configured',
  healthy: 'Healthy',
  unhealthy: 'Unhealthy',
  disabled: 'Disabled',
}
