export type LogLevel = 'debug' | 'info' | 'warn' | 'error'

export interface FrontendLogEntry {
  id: string
  timestamp: string
  level: LogLevel
  source: 'frontend'
  component: string
  message: string
  url: string
  userAgent: string
  extra?: Record<string, unknown>
}

type LogListener = (entry: FrontendLogEntry) => void

const MAX_LOG_ENTRIES = 1000
const API_BASE_URL = import.meta.env.VITE_API_URL || ''

const entries: FrontendLogEntry[] = []
const listeners = new Set<LogListener>()

function notify(entry: FrontendLogEntry) {
  for (const listener of listeners) {
    listener(entry)
  }
}

function pushEntry(entry: FrontendLogEntry) {
  if (entries.length >= MAX_LOG_ENTRIES) {
    entries.shift()
  }
  entries.push(entry)
  notify(entry)
}

function getBrowserMetadata() {
  if (typeof window === 'undefined') {
    return {
      url: '',
      userAgent: '',
    }
  }

  return {
    url: window.location.href,
    userAgent: window.navigator.userAgent,
  }
}

function writeConsole(entry: FrontendLogEntry) {
  if (!import.meta.env.DEV) {
    return
  }

  const payload = [`[${entry.level}]`, `[${entry.component}]`, entry.message, entry.extra]
  const method = entry.level === 'debug' ? 'debug' : entry.level === 'info' ? 'info' : entry.level
  console[method](...payload)
}

function sendToBackend(entry: FrontendLogEntry) {
  if (entry.level !== 'warn' && entry.level !== 'error') {
    return
  }

  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null

  void fetch(`${API_BASE_URL}/api/v1/system/logs`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      timestamp: entry.timestamp,
      level: entry.level,
      source: entry.source,
      component: entry.component,
      message: entry.message,
      url: entry.url,
      user_agent: entry.userAgent,
      extra: entry.extra,
    }),
  }).catch(() => {
    // Backend unreachable — persist to localStorage so logs aren't lost
    try {
      const key = 'kos_pending_logs'
      const pending: unknown[] = JSON.parse(localStorage.getItem(key) || '[]')
      pending.push(entry)
      // Keep last 200 to avoid filling storage
      if (pending.length > 200) pending.splice(0, pending.length - 200)
      localStorage.setItem(key, JSON.stringify(pending))
    } catch {
      // localStorage full or unavailable — give up
    }
  })
}

/** Retry sending any queued logs from localStorage. */
export function flushPendingLogs(): void {
  try {
    const key = 'kos_pending_logs'
    const raw = localStorage.getItem(key)
    if (!raw) return
    const pending: FrontendLogEntry[] = JSON.parse(raw)
    if (!pending.length) return
    localStorage.removeItem(key)

    const token = localStorage.getItem('access_token')
    const batch = pending.slice(0, 50) // Send in batches
    const remaining = pending.slice(50)
    if (remaining.length) {
      localStorage.setItem(key, JSON.stringify(remaining))
    }

    void fetch(`${API_BASE_URL}/api/v1/system/logs`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        batch: batch.map((e) => ({
          timestamp: e.timestamp,
          level: e.level,
          source: e.source,
          component: e.component,
          message: e.message,
          url: e.url,
          user_agent: e.userAgent,
          extra: e.extra,
        })),
      }),
    }).catch(() => {
      // Still unreachable — put back
      const existing: unknown[] = JSON.parse(localStorage.getItem(key) || '[]')
      existing.push(...batch)
      if (existing.length > 200) existing.splice(0, existing.length - 200)
      localStorage.setItem(key, JSON.stringify(existing))
    })
  } catch {
    // ignore
  }
}

function createEntry(level: LogLevel, component: string, message: string, extra?: Record<string, unknown>): FrontendLogEntry {
  const metadata = getBrowserMetadata()

  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
    timestamp: new Date().toISOString(),
    level,
    source: 'frontend',
    component,
    message,
    url: metadata.url,
    userAgent: metadata.userAgent,
    extra,
  }
}

function log(level: LogLevel, component: string, message: string, extra?: Record<string, unknown>) {
  const entry = createEntry(level, component, message, extra)
  pushEntry(entry)
  writeConsole(entry)
  sendToBackend(entry)
  return entry
}

export const logger = {
  debug: (component: string, message: string, extra?: Record<string, unknown>) => log('debug', component, message, extra),
  info: (component: string, message: string, extra?: Record<string, unknown>) => log('info', component, message, extra),
  warn: (component: string, message: string, extra?: Record<string, unknown>) => log('warn', component, message, extra),
  error: (component: string, message: string, extra?: Record<string, unknown>) => log('error', component, message, extra),
  getEntries: () => [...entries],
  subscribe(listener: LogListener) {
    listeners.add(listener)
    return () => {
      listeners.delete(listener)
    }
  },
}
