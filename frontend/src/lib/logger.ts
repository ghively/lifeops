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
  }).catch(() => undefined)
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
