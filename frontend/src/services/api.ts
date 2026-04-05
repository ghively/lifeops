import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_URL || ''

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
      originalRequest._retry = true

      try {
        const refreshToken = localStorage.getItem('refresh_token')
        if (!refreshToken) {
          // No refresh token, redirect to login
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
          window.location.href = '/login'
          return Promise.reject(error)
        }

        // Try to refresh token
        const response = await axios.post<AuthTokens>(
          `${API_BASE_URL}/api/v1/auth/refresh`,
          { refresh_token: refreshToken },
          { headers: { 'Content-Type': 'application/json' } }
        )

        const { access_token, refresh_token } = response.data

        // Store new tokens
        localStorage.setItem('access_token', access_token)
        if (refresh_token) {
          localStorage.setItem('refresh_token', refresh_token)
        }

        // Retry original request
        originalRequest.headers.Authorization = `Bearer ${access_token}`
        return api(originalRequest)
      } catch (refreshError) {
        // Refresh failed, clear tokens and redirect to login
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
        window.location.href = '/login'
        return Promise.reject(refreshError)
      }
    }

    if (error.response) {
      const message = (error.response.data as { detail?: string })?.detail || 'An error occurred'
      throw new APIError(message, error.response.status, error.response.data)
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

export const systemApi = {
  getLogs: (params?: { level?: string; limit?: number; source?: string; search?: string }) =>
    api.get<{ logs: SystemLogEntry[]; count: number }>('/system/logs', { params }).then((r) => r.data),

  getStatus: () =>
    api.get<SystemStatus>('/system/status').then((r) => r.data),
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
