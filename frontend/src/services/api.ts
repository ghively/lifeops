import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_URL || ''
const AUTH_REFRESH_PATH = '/api/v1/auth/refresh'

// H69: BroadcastChannel for cross-tab logout coordination
const logoutChannel = typeof BroadcastChannel !== 'undefined'
  ? new BroadcastChannel('auth-logout')
  : null

if (logoutChannel) {
  logoutChannel.addEventListener('message', (event) => {
    if (event.data?.type === 'logout') {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      window.location.href = '/login'
    }
  })
}

// Type definitions
export interface ObjectItem {
  id: string
  type: string
  title: string
  icon?: string
  content?: string
  properties?: Record<string, unknown>
  layout?: string
}

export interface BlockItem {
  id: string
  object_id: string
  type: string
  content: string
  level: number
  order: number
  properties?: Record<string, unknown>
  parent_id?: string | null
}

export interface TaskItem extends ObjectItem {
  properties: {
    status: 'todo' | 'in-progress' | 'blocked' | 'review' | 'done'
    priority: 'low' | 'medium' | 'high' | 'urgent'
    assigned_to?: string
    due_date?: string
    [key: string]: unknown
  }
}

export interface AgentItem {
  id: string
  name: string
  description?: string
  status: 'active' | 'idle' | 'busy' | 'offline' | 'working' | 'error'
  capabilities?: string[]
  current_task?: string
  current_action?: string
  last_seen?: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'agent' | 'system'
  content: string
  timestamp: string
  agent_name?: string
  metadata?: Record<string, unknown>
}

export interface RuntimeChatEvent {
  type: 'text_delta' | 'tool_start' | 'tool_result' | 'thinking' | 'subagent_start' | 'subagent_result' | 'approval_required' | 'security_warning' | 'done' | 'error'
  session_id?: string
  agent_id?: string
  message?: string
  delta?: string
  tool_name?: string
  data?: Record<string, unknown>
}

export interface AgentApprovalRequest {
  request_id: string
  agent_id?: string
  session_id?: string
  tool_name: string
  description?: string
  arguments?: Record<string, unknown>
  timeout_seconds?: number
}

export interface AgentUsageCurrent {
  agent_id: string
  user_id: string
  minute_requests: number
  minute_limit: number
  daily_tokens: number
  daily_token_limit: number
  daily_requests: number
  retry_after_seconds: number
  date?: string | null
}

export interface AgentUsageHistoryItem {
  id: string
  agent_id: string
  user_id: string
  date: string
  total_tokens: number
  total_requests: number
  created_at?: string | null
}

export interface AgentUsageResponse {
  current: AgentUsageCurrent
  history: AgentUsageHistoryItem[]
}

interface AgentRateLimitErrorPayload {
  detail?: string
  retry_after_seconds?: number
}

export interface AgentAuditItem {
  id: string
  agent_id: string
  session_id?: string | null
  user_id?: string | null
  event_type: string
  details: Record<string, unknown>
  created_at?: string | null
}

export interface AgentAuditResponse {
  items: AgentAuditItem[]
  total: number
}

export interface AgentChatRequest {
  agent_id: string
  message: string
  session_id?: string | null
  shared_context?: Record<string, unknown>
}

export interface AgentChatResponse {
  response: Response
}

export interface CLIAgentAvailability {
  installed: boolean
  command?: string
  description?: string
  error?: string | null
}

export interface CLIAgentStatus {
  agents: Record<string, CLIAgentAvailability>
}

export interface AgentFile {
  name: 'AGENT.md' | 'SOUL.md' | 'MEMORY.md' | 'TOOLS.md'
  content: string
}

export interface AgentSession {
  id: string
  agent_id: string
  title?: string | null
  created_at: string
  updated_at: string
  message_count: number
  metadata?: Record<string, unknown>
}

export interface AgentTemplate {
  id: string
  name: string
  description: string
  files: Record<string, string>
}

export interface ScheduledTask {
  id: string
  agent_id: string
  name: string
  cron_expression: string
  task_type: 'periodic_research' | 'memory_curation' | 'data_cleanup' | 'webhook_triggered'
  config: Record<string, unknown>
  enabled: boolean
  last_run?: string | null
  next_run?: string | null
  created_at?: string | null
}

export interface ScheduledTaskInput {
  agent_id: string
  name: string
  cron_expression: string
  task_type: ScheduledTask['task_type']
  config?: Record<string, unknown>
  enabled?: boolean
}

export interface AgentWebhook {
  id: string
  agent_id: string
  name: string
  url_path: string
  secret: string
  event_type: string
  enabled: boolean
  created_at?: string | null
}

export interface RuntimeAgentMessage {
  id?: string
  role: 'system' | 'user' | 'assistant' | 'tool'
  content: string
  name?: string | null
  tool_calls?: Array<Record<string, unknown>>
  tool_results?: Array<Record<string, unknown>>
  tokens_in?: number
  tokens_out?: number
  created_at?: string | null
  metadata?: Record<string, unknown>
}

export interface MCPToolItem {
  name: string
  server_name: string
  runtime_name: string
  description: string
  input_schema: Record<string, unknown>
}

export interface MCPServerItem {
  name: string
  transport: 'stdio' | 'http'
  connected: boolean
  state: 'connected' | 'disconnected' | 'error'
  enabled: boolean
  auto_connect: boolean
  tool_count: number
  tools: MCPToolItem[]
  error?: string | null
  last_checked_at?: string | null
  last_connected_at?: string | null
}

export interface MCPServerConfigInput {
  name: string
  transport: 'stdio' | 'http'
  command?: string
  args?: string[]
  env?: Record<string, string>
  url?: string
  headers?: Record<string, string>
  timeout_seconds?: number
  enabled?: boolean
  auto_connect?: boolean
}

export interface FileItem {
  id: string
  name?: string
  filename?: string
  path: string
  file_type?: string
  content_type?: string
  mime_type?: string
  indexed?: boolean
  indexed_at?: string
  last_indexed?: string
  last_modified?: string
  hash?: string
  checksum?: string
  size_bytes?: number
  index_status?: 'pending' | 'processing' | 'indexed' | 'error'
  error_message?: string | null
}

export interface SearchResult {
  id: string
  type?: string
  title?: string
  content?: string
  context?: string
  filename?: string
  score: number
  collection: string
}

export interface WatchedFolder {
  id: string
  path: string
  recursive: boolean
  file_count: number
}

export interface RelationItem {
  id: string
  source_id: string
  source_type: 'object' | 'block'
  target_id: string
  target_type: 'object' | 'block'
  relation_type: string
  context?: string
  created_at?: string
  updated_at?: string
}

export interface AppSettings {
  openclaw_url: string
  openclaw_token?: string
  openclaw_enabled?: boolean
  backup_snapshots: boolean
  backup_markdown: boolean
  backup_git: boolean
  git_repo_url?: string
  snapshot_interval_hours?: number
  markdown_export_interval_hours?: number
  git_sync_interval_minutes?: number
  embedding_model?: string
  image_embedding_model?: string
  max_context_tokens?: number
  auto_index: boolean
}

export interface SystemLogEntry {
  timestamp?: string
  level: string
  source: string
  logger?: string
  message: string
  request_id?: string
  data?: Record<string, unknown>
}

export interface SystemStatus {
  version: string
  uptime_seconds: number
  request_counts: {
    total: number
  }
  error_counts: {
    total: number
  }
  active_websocket_connections: {
    system: number
    collaboration: number
    total: number
  }
}

// Auth types
export interface User {
  id: string
  email: string
  username: string
  display_name?: string
  is_active: boolean
  created_at: string
  updated_at?: string
}

export interface AuthTokens {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
  user: User
}

export interface RegisterData {
  email: string
  username: string
  display_name?: string
  password: string
}

export interface LoginData {
  email: string
  password: string
}

export interface PasswordResetData {
  email: string
}

export interface PasswordResetConfirmData {
  token: string
  new_password: string
}

// Error handling
export class APIError extends Error {
  constructor(
    message: string,
    public statusCode?: number,
    public response?: unknown
  ) {
    super(message)
    this.name = 'APIError'
  }
}

// Axios instance
export const api = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
})

// H71: Zustand store is the source of truth for auth tokens.
// localStorage reads here are fallbacks for edge cases (e.g., before store initializes).
function getAuthToken() {
  return localStorage.getItem('access_token')
}

function getApiBaseUrl() {
  if (API_BASE_URL) {
    return `${API_BASE_URL}/api/v1`
  }

  if (typeof window !== 'undefined') {
    return `${window.location.origin}/api/v1`
  }

  return '/api/v1'
}

export function createAuthenticatedRequestHeaders(init?: HeadersInit) {
  const headers = new Headers(init)
  const token = getAuthToken()
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  return headers
}

// Request interceptor to add auth token
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// H67: Retry interceptor for idempotent GET requests with exponential backoff
api.interceptors.response.use(undefined, async (error: unknown, retryCount = 0) => {
  if (!axios.isAxiosError(error)) return Promise.reject(error)
  const originalRequest = error.config as InternalAxiosRequestConfig & { _retryCount?: number }
  if (!originalRequest) return Promise.reject(error)

  const isIdempotent = originalRequest.method === 'get'
  const isNetworkError = !error.response
  const isRetryableStatus = error.response?.status != null && error.response.status >= 500 && error.response.status < 600

  if (isIdempotent && (isNetworkError || isRetryableStatus) && retryCount < 3) {
    const count = originalRequest._retryCount ?? retryCount
    const delay = Math.min(1000 * Math.pow(2, count), 8000)
    await new Promise((r) => setTimeout(r, delay))
    originalRequest._retryCount = count + 1
    return api(originalRequest)
  }
  return Promise.reject(error)
})

// Mutex to prevent multiple simultaneous token refresh attempts
let isRefreshing = false
let failedQueue: Array<{
  resolve: (token: string) => void
  reject: (error: unknown) => void
}> = []

function processQueue(error: unknown, token: string | null = null) {
  failedQueue.forEach(({ resolve, reject }) => {
    if (token) {
      resolve(token)
    } else {
      reject(error)
    }
  })
  failedQueue = []
}

// Response interceptor for error handling and token refresh
api.interceptors.response.use(
  (response) => response,
  async (error: unknown) => {
    if (!axios.isAxiosError(error)) {
      throw new APIError('An unknown error occurred')
    }

    const originalRequest = error.config as (InternalAxiosRequestConfig & { _retry?: boolean }) | undefined

    // If 401 and not already tried to refresh
    if (error.response?.status === 401 && originalRequest && !originalRequest._retry) {
      // If already refreshing, queue this request
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({
            resolve: (token: string) => {
              originalRequest.headers.Authorization = `Bearer ${token}`
              resolve(api(originalRequest))
            },
            reject,
          })
        })
      }

      originalRequest._retry = true
      isRefreshing = true

      try {
        const refreshToken = localStorage.getItem('refresh_token')
        if (!refreshToken) {
          // No refresh token, clear state and redirect once (H69: broadcast logout)
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
          isRefreshing = false
          processQueue(error, null)
          logoutChannel?.postMessage({ type: 'logout' })
          window.location.href = '/login'
          return Promise.reject(error)
        }

        // Try to refresh token (H68: use constant)
        const response = await axios.post<AuthTokens>(
          `${API_BASE_URL}${AUTH_REFRESH_PATH}`,
          { refresh_token: refreshToken },
          { headers: { 'Content-Type': 'application/json' } }
        )

        const { access_token, refresh_token } = response.data

        // Store new tokens
        localStorage.setItem('access_token', access_token)
        if (refresh_token) {
          localStorage.setItem('refresh_token', refresh_token)
        }

        isRefreshing = false
        processQueue(null, access_token)

        // Retry original request
        originalRequest.headers.Authorization = `Bearer ${access_token}`
        return api(originalRequest)
      } catch (refreshError) {
        isRefreshing = false
        processQueue(refreshError, null)
        // Refresh failed, clear tokens and redirect once (H69: broadcast logout)
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
        logoutChannel?.postMessage({ type: 'logout' })
        window.location.href = '/login'
        return Promise.reject(refreshError)
      }
    }

    if (error.response) {
      const message = (error.response.data as { detail?: string })?.detail || 'An error occurred'
      const status = error.response.status
      // Log 4xx/5xx errors for monitoring (H73)
      if (status >= 400) {
        const { logger } = await import('@/lib/logger')
        logger.error('api', `HTTP ${status}: ${message}`, {
          url: originalRequest?.url,
          method: originalRequest?.method,
          status,
        })
      }
      throw new APIError(message, status, error.response.data)
    }
    throw new APIError(error.message || 'Network error')
  }
)

// Objects API
export const objectsApi = {
  list: (params?: { type?: string; limit?: number; offset?: number }) =>
    api.get<{ objects: ObjectItem[]; total: number }>('/objects', { params }).then((r) => r.data),

  get: (id: string) =>
    api.get<ObjectItem>(`/objects/${id}`).then((r) => r.data),

  create: (data: {
    type: string
    title: string
    icon?: string
    content?: string
    properties?: Record<string, unknown>
    layout?: string
  }) => api.post<ObjectItem>('/objects', data).then((r) => r.data),

  update: (id: string, data: Partial<ObjectItem>) =>
    api.put<ObjectItem>(`/objects/${id}`, data).then((r) => r.data),

  delete: (id: string) =>
    api.delete(`/objects/${id}`).then((r) => r.data),

  getRelations: (id: string) =>
    api.get<{ relations: RelationItem[] }>(`/relations/object/${id}`).then((r) => r.data),
}

// Blocks API
export const blocksApi = {
  getForObject: (objectId: string) =>
    api.get<{ blocks: BlockItem[] }>(`/blocks/object/${objectId}`).then((r) => r.data),

  create: (objectId: string, data: {
    id?: string
    content: string
    type?: string
    level?: number
    properties?: Record<string, unknown>
    parent_id?: string | null
    order?: number
  }) => api.post<BlockItem>('/blocks', { object_id: objectId, ...data }).then((r) => r.data),

  update: (id: string, data: Partial<BlockItem>) =>
    api.put<BlockItem>(`/blocks/${id}`, data).then((r) => r.data),

  batchUpdate: (blocks: { id: string; order: number; parent_id?: string | null; level?: number }[]) =>
    api.post('/blocks/batch-update', { blocks }).then((r) => r.data),

  syncForObject: (objectId: string, blocks: Array<{
    id: string
    content: string
    type?: string
    level?: number
    order?: number
    parent_id?: string | null
    properties?: Record<string, unknown>
  }>) => api.put(`/blocks/object/${objectId}/sync`, { blocks }).then((r) => r.data),

  delete: (id: string) =>
    api.delete(`/blocks/${id}`).then((r) => r.data),
}

// Tasks API
export const tasksApi = {
  list: (params?: { status?: string; priority?: string; assigned_to?: string }) =>
    api.get<{ tasks: TaskItem[]; by_status: Record<string, number>; by_priority: Record<string, number> }>('/tasks', { params }).then((r) => r.data),

  get: (id: string) =>
    api.get<TaskItem>(`/tasks/${id}`).then((r) => r.data),

  assign: (taskId: string, data: {
    agent_name: string
    priority: string
    include_context?: boolean
    additional_context?: string[]
  }) => api.post(`/tasks/${taskId}/assign`, data).then((r) => r.data),

  updateStatus: (taskId: string, data: {
    agent_name: string
    status: string
    current_action?: string
    notes?: string
  }) => api.post(`/tasks/${taskId}/status`, data).then((r) => r.data),

  getContext: (taskId: string) =>
    api.get<{ context: unknown }>(`/tasks/${taskId}/context`).then((r) => r.data),
}

// Agents API
export const agentsApi = {
  list: () =>
    api.get<{ agents: AgentItem[] }>('/agents').then((r) => r.data),

  get: (name: string) =>
    api.get<AgentItem>(`/agents/${name}`).then((r) => r.data),

  getTasks: (name: string, params?: { status?: string }) =>
    api.get<{ tasks: TaskItem[] }>(`/agents/${name}/tasks`, { params }).then((r) => r.data),

  chat: (name: string, content: string, sessionId?: string) =>
    api.post(`/agents/${name}/chat`, { content, session_id: sessionId }).then((r) => r.data),

  getChatHistory: (name: string, sessionId?: string) =>
    api.get<{ messages: ChatMessage[] }>(`/agents/${name}/chat`, { params: { session_id: sessionId } }).then((r) => r.data),

  getMemories: (name: string, query?: string) =>
    api.get<{ memories: unknown[] }>(`/agents/${name}/memories`, { params: { query } }).then((r) => r.data),
}

export const agentRuntimeApi = {
  list: () =>
    api.get<{ agents: Array<{ id: string; path: string }> }>('/agents/runtime').then((r) => r.data),

  listTemplates: () =>
    api.get<{ templates: AgentTemplate[] }>('/agents/runtime/templates').then((r) => r.data),

  createAgent: (agentId: string, templateId?: string | null) =>
    api.post<{ id: string; path: string }>(`/agents/runtime/${agentId}`, { template_id: templateId || undefined }).then((r) => r.data),

  createFromTemplate: (agentId: string, templateId: string) =>
    api.post<{ id: string; path: string }>('/agents/runtime/create-from-template', { agent_id: agentId, template_id: templateId }).then((r) => r.data),

  deleteAgent: (agentId: string) =>
    api.delete<{ deleted: boolean; agent_id: string }>(`/agents/runtime/${agentId}`).then((r) => r.data),

  getAgentFile: async (agentId: string, name: AgentFile['name']) => {
    const response = await api.get<string>(`/agents/runtime/${agentId}/files/${name}`, {
      responseType: 'text' as const,
    })

    return {
      name,
      content: response.data,
    } satisfies AgentFile
  },

  updateAgentFile: (agentId: string, name: AgentFile['name'], content: string) =>
    api.put<{ updated: boolean; agent_id: string; file: string }>(`/agents/runtime/${agentId}/files/${name}`, { content }).then((r) => r.data),

  getAgentSessions: (agentId?: string) =>
    api.get<{ sessions: AgentSession[] }>('/agents/runtime/sessions', { params: { agent_id: agentId } }).then((r) => r.data),

  getSessionMessages: (sessionId: string) =>
    api.get<{ messages: RuntimeAgentMessage[] }>(`/agents/runtime/sessions/${sessionId}/messages`).then((r) => r.data),

  deleteSession: (sessionId: string) =>
    api.delete<{ deleted: boolean; session_id: string }>(`/agents/runtime/sessions/${sessionId}`).then((r) => r.data),

  createScheduledTask: (data: ScheduledTaskInput) =>
    api.post<ScheduledTask>('/agents/runtime/schedule', data).then((r) => r.data),

  listScheduledTasks: (agentId?: string) =>
    api.get<{ tasks: ScheduledTask[] }>('/agents/runtime/schedule', { params: { agent_id: agentId } }).then((r) => r.data),

  deleteScheduledTask: (taskId: string) =>
    api.delete<{ deleted: boolean; id: string }>(`/agents/runtime/schedule/${taskId}`).then((r) => r.data),

  runScheduledTaskNow: (taskId: string) =>
    api.post<{ task: ScheduledTask; result: Record<string, unknown> }>(`/agents/runtime/schedule/${taskId}/run`).then((r) => r.data),

  curateMemory: (agentId: string, frequency: string = 'daily') =>
    api.post(`/agents/runtime/${agentId}/curate-memory`, { frequency }).then((r) => r.data),

  createWebhook: (data: { agent_id: string; name: string; event_type: string; enabled?: boolean }) =>
    api.post<AgentWebhook>('/agents/runtime/webhooks', data).then((r) => r.data),

  listWebhooks: (agentId?: string) =>
    api.get<{ webhooks: AgentWebhook[] }>('/agents/runtime/webhooks', { params: { agent_id: agentId } }).then((r) => r.data),

  deleteWebhook: (webhookId: string) =>
    api.delete<{ deleted: boolean; id: string }>(`/agents/runtime/webhooks/${webhookId}`).then((r) => r.data),

  getCLIAgentStatus: () =>
    api.get<CLIAgentStatus>('/agents/runtime/cli-status').then((r) => r.data),

  getUsage: (agentId: string) =>
    api.get<AgentUsageResponse>(`/agents/runtime/${agentId}/usage`).then((r) => r.data),

  getAuditLog: (agentId: string, params?: { page?: number; page_size?: number }) =>
    api.get<AgentAuditResponse>(`/agents/runtime/${agentId}/audit`, { params }).then((r) => r.data),

  listMCPServers: () =>
    api.get<{ servers: MCPServerItem[] }>('/agents/runtime/mcp/servers').then((r) => r.data),

  createMCPServer: (data: MCPServerConfigInput) =>
    api.post<MCPServerItem>('/agents/runtime/mcp/servers', data).then((r) => r.data),

  deleteMCPServer: (name: string) =>
    api.delete<{ deleted: boolean; name: string }>(`/agents/runtime/mcp/servers/${encodeURIComponent(name)}`).then((r) => r.data),

  connectMCPServer: (name: string) =>
    api.post<MCPServerItem>(`/agents/runtime/mcp/servers/${encodeURIComponent(name)}/connect`).then((r) => r.data),

  disconnectMCPServer: (name: string) =>
    api.post<MCPServerItem>(`/agents/runtime/mcp/servers/${encodeURIComponent(name)}/disconnect`).then((r) => r.data),

  getMCPServerTools: (name: string) =>
    api.get<{ server: MCPServerItem; tools: MCPToolItem[] }>(`/agents/runtime/mcp/servers/${encodeURIComponent(name)}/tools`).then((r) => r.data),

  testMCPServer: (data: MCPServerConfigInput) =>
    api.post<{ success: boolean; tools: MCPToolItem[]; status: MCPServerItem }>('/agents/runtime/mcp/test', data).then((r) => r.data),

  chatWithAgent: async (data: AgentChatRequest, signal?: AbortSignal): Promise<AgentChatResponse> => {
    const response = await fetch(`${getApiBaseUrl()}/agents/runtime/chat`, {
      method: 'POST',
      headers: createAuthenticatedRequestHeaders({
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      }),
      body: JSON.stringify(data),
      signal,
    })

    if (!response.ok) {
      let message = 'Failed to start agent chat'
      let payload: AgentRateLimitErrorPayload | null = null
      try {
        payload = await response.json() as AgentRateLimitErrorPayload
        if (payload.detail) {
          message = payload.detail
        }
      } catch {
        // Ignore malformed error bodies.
      }
      throw new APIError(message, response.status, payload)
    }

    return { response }
  },
}

// Search API
export const searchApi = {
  search: (query: string, type: 'semantic' | 'exact' = 'semantic', params?: { collection?: string; limit?: number }) =>
    api.get<{ results: SearchResult[] }>('/search', { params: { q: query, exact: type === 'exact', ...params } }).then((r) => r.data),

  findSimilar: (objectId: string, params?: { collection?: string; limit?: number }) =>
    api.get<{ results: SearchResult[] }>(`/search/similar/${objectId}`, { params }).then((r) => r.data),
}

// Files API
export const filesApi = {
  list: () =>
    api.get<{ files: FileItem[] }>('/files').then((r) => r.data),

  get: (id: string) =>
    api.get<FileItem>(`/files/${id}`).then((r) => r.data),

  reindex: (id: string) =>
    api.post(`/files/${id}/reindex`).then((r) => r.data),
}

// Settings API
export const settingsApi = {
  get: () =>
    api.get<AppSettings>('/settings').then((r) => r.data),

  update: (data: Partial<AppSettings>) =>
    api.put<AppSettings>('/settings', data).then((r) => r.data),

  getWatchedFolders: () =>
    api.get<{ folders: WatchedFolder[] }>('/settings/watched-folders').then((r) => r.data),

  addWatchedFolder: (path: string, recursive: boolean = true, includePatterns?: string[], excludePatterns?: string[]) =>
    api.post<WatchedFolder>('/settings/watched-folders', {
      path,
      recursive,
      include_patterns: includePatterns,
      exclude_patterns: excludePatterns,
    }).then((r) => r.data),

  removeWatchedFolder: (id: string) =>
    api.delete(`/settings/watched-folders/${id}`).then((r) => r.data),

  triggerBackup: (type: 'snapshot' | 'markdown' | 'git') =>
    api.post('/settings/backup', { type }).then((r) => r.data),
}

export interface SmokeTestResult {
  status: 'pass' | 'fail'
  duration_ms: number
  results: Record<string, { status: 'pass' | 'fail' | 'warn' | 'skip'; message: string }>
}

export const systemApi = {
  getLogs: (params?: { level?: string; limit?: number; source?: string; search?: string }) =>
    api.get<{ logs: SystemLogEntry[]; count: number }>('/system/logs', { params }).then((r) => r.data),

  getUnifiedLogs: (params?: { level?: string; limit?: number; source?: string; search?: string }) =>
    api.get<{ logs: SystemLogEntry[]; count: number }>('/system/logs/unified', { params }).then((r) => r.data),

  getStatus: () =>
    api.get<SystemStatus>('/system/status').then((r) => r.data),

  smokeTest: () =>
    api.get<SmokeTestResult>('/system/smoke-test').then((r) => r.data),
}

// Relations API
export const relationsApi = {
  create: (data: {
    source_id: string
    target_id: string
    relation_type: string
    source_type?: 'object' | 'block'
    target_type?: 'object' | 'block'
    context?: string
  }) => api.post('/relations', data).then((r) => r.data),

  delete: (id: string) =>
    api.delete(`/relations/${id}`).then((r) => r.data),

  getForObject: (objectId: string) =>
    api.get<{ relations: RelationItem[] }>(`/relations/object/${objectId}`).then((r) => r.data),
}

// Auth API
export const authApi = {
  register: (data: RegisterData) =>
    api.post<AuthTokens>('/auth/register', data).then((r) => r.data),

  login: (email: string, password: string) =>
    api.post<AuthTokens>('/auth/login', { email, password }).then((r) => r.data),

  logout: (refreshToken: string) =>
    api.post('/auth/logout', { refresh_token: refreshToken }).then((r) => r.data),

  refreshToken: (refreshToken: string) =>
    api.post<AuthTokens>('/auth/refresh', { refresh_token: refreshToken }).then((r) => r.data),

  getMe: () =>
    api.get<User>('/auth/me').then((r) => r.data),

  requestPasswordReset: (email: string) =>
    api.post<{ message: string; _dev_token?: string }>('/auth/password-reset', { email }).then((r) => r.data),

  confirmPasswordReset: (token: string, newPassword: string) =>
    api.post<{ message: string }>('/auth/password-reset/confirm', { token, new_password: newPassword }).then((r) => r.data),
}

// WebSocket API (for reference - actual WebSocket handled by useWebSocket hook)
export const websocketApi = {
  getUrl: (endpoint: string) => `${API_BASE_URL.replace('http', 'ws')}/ws/${endpoint}`,
}
