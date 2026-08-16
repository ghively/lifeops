/**
 * Frontend logger.
 *
 * Keeps an in-memory ring for inspection and mirrors warn/error entries to
 * LifeOps Core (`POST /system/logs`) so the server sees what the Console
 * suffered. The remote sink is batched and best-effort: it never throws,
 * never awaits in the caller's path, and never logs its own failures (a
 * logging loop is worse than a lost log).
 *
 * Secret hygiene: context values whose keys look like credentials are
 * redacted before leaving the browser. The auth token never appears here —
 * it lives only in the axios interceptor.
 */

import { systemApi, type RemoteLogEntry } from '@/services/lifeops'

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
const FLUSH_INTERVAL_MS = 5_000
const FLUSH_BATCH_SIZE = 10
const MAX_BATCH = 50

/** Keys that must never leave the browser in a log payload. */
const SENSITIVE_KEY = /password|secret|token|authorization|api[-_]?key|credential/i

const entries: FrontendLogEntry[] = []
const listeners = new Set<LogListener>()

const remoteQueue: RemoteLogEntry[] = []
let flushTimer: ReturnType<typeof setTimeout> | null = null
let flushing = false

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

function redact(context: Record<string, unknown>): Record<string, unknown> {
  const clean: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(context)) {
    clean[key] = SENSITIVE_KEY.test(key) ? '[redacted]' : value
  }
  return clean
}

function toRemoteEntry(entry: FrontendLogEntry): RemoteLogEntry {
  return {
    level: entry.level,
    message: entry.message,
    ts: entry.timestamp,
    context: redact({
      component: entry.component,
      url: entry.url,
      user_agent: entry.userAgent,
      ...entry.extra,
    }),
  }
}

/**
 * Send the queued batch. Failures are dropped on purpose: the queue is a
 * convenience, not a guarantee, and retrying an unreachable server on every
 * warning would amplify an outage into request spam.
 */
async function flushRemote() {
  if (flushing || remoteQueue.length === 0) {
    return
  }
  flushing = true
  const batch = remoteQueue.splice(0, MAX_BATCH)
  try {
    await systemApi.postLogs(batch)
  } catch {
    // best-effort — see the docstring above
  } finally {
    flushing = false
    if (remoteQueue.length > 0) {
      scheduleFlush()
    }
  }
}

function scheduleFlush() {
  if (flushTimer !== null) {
    return
  }
  flushTimer = setTimeout(() => {
    flushTimer = null
    void flushRemote()
  }, FLUSH_INTERVAL_MS)
}

function enqueueRemote(entry: FrontendLogEntry) {
  if (entry.level !== 'warn' && entry.level !== 'error') {
    return
  }
  remoteQueue.push(toRemoteEntry(entry))
  if (remoteQueue.length >= FLUSH_BATCH_SIZE) {
    void flushRemote()
  } else {
    scheduleFlush()
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
  enqueueRemote(entry)
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

/** Test hook: flush the remote queue immediately and reset timers. */
export function _flushRemoteForTest(): Promise<void> {
  if (flushTimer !== null) {
    clearTimeout(flushTimer)
    flushTimer = null
  }
  return flushRemote()
}
