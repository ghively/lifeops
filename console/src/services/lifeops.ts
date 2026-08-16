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

const BASE_URL: string =
  (import.meta.env.VITE_LIFEOPS_URL as string | undefined) ?? 'http://127.0.0.1:8080'

export const lifeops: AxiosInstance = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
    // Identifies the Console to LifeOps policy. The server decides what this
    // identity may do; the header only declares who is asking.
    'X-LifeOps-Client': 'lifeops-console',
  },
  timeout: 30000,
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

lifeops.interceptors.response.use(
  (response) => response,
  (error) => {
    const body = error?.response?.data as LifeOpsErrorBody | undefined
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

export interface SystemConfig {
  display_name: string
  timezone: string
  household_name: string
  primary_person_id: string | null
  local_url: string | null
  setup_completed: boolean
  safe_mode: boolean
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

// --- API surface -------------------------------------------------------------

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

export const systemApi = {
  status: () => lifeops.get<SystemStatus>('/system/status').then((r) => r.data),
  health: () =>
    lifeops
      .get<{ status: string; components: Record<string, ComponentHealth | boolean> }>(
        '/health',
      )
      .then((r) => r.data),
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

/**
 * Which states a task may legally move to next.
 *
 * This mirrors the server's transition table so the UI can offer only valid
 * choices. LifeOps Core remains the authority — it re-validates every
 * transition and rejects an illegal one with `invalid_transition`.
 */
export const TASK_TRANSITIONS: Record<TaskState, TaskState[]> = {
  CAPTURED: ['PLANNED', 'READY', 'BLOCKED', 'CANCELLED'],
  PLANNED: ['READY', 'CAPTURED', 'BLOCKED', 'CANCELLED'],
  READY: ['EXECUTING', 'PLANNED', 'BLOCKED', 'CANCELLED'],
  EXECUTING: [
    'WAITING_EXTERNAL',
    'NEEDS_APPROVAL',
    'VERIFYING',
    'COMPLETED',
    'BLOCKED',
    'FAILED',
    'CANCELLED',
  ],
  WAITING_EXTERNAL: [
    'EXECUTING',
    'NEEDS_APPROVAL',
    'VERIFYING',
    'BLOCKED',
    'FAILED',
    'CANCELLED',
  ],
  NEEDS_APPROVAL: ['EXECUTING', 'BLOCKED', 'FAILED', 'CANCELLED'],
  VERIFYING: ['COMPLETED', 'WAITING_EXTERNAL', 'BLOCKED', 'FAILED'],
  BLOCKED: ['READY', 'PLANNED', 'EXECUTING', 'FAILED', 'CANCELLED'],
  FAILED: ['READY', 'PLANNED', 'CANCELLED'],
  COMPLETED: [],
  CANCELLED: [],
}

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
