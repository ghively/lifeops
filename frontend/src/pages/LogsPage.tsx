import { useCallback, useEffect, useMemo, useState } from 'react'
import { Download, Loader2, ScrollText } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'

import { logger, type FrontendLogEntry } from '@/lib/logger'
import { useWebSocket } from '@/hooks/useWebSocket'
import { systemApi, type SystemLogEntry, type SystemStatus } from '@/services/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { QueryError } from '@/components/QueryError'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

type SourceFilter = 'all' | 'backend' | 'frontend'
type LevelFilter = 'all' | 'debug' | 'info' | 'warn' | 'error'

interface DisplayLogEntry {
  timestamp: string
  level: string
  source: string
  message: string
  logger?: string
  request_id?: string
  data?: Record<string, unknown>
}

const LOG_WS_URL = (() => {
  const configuredApiUrl = import.meta.env.VITE_API_URL as string | undefined
  if (configuredApiUrl) {
    return `${configuredApiUrl.replace(/^http/, 'ws')}/ws/system`
  }

  if (typeof window !== 'undefined') {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${protocol}//${window.location.host}/ws/system`
  }

  return '/ws/system'
})()

function normalizeFrontendLog(entry: FrontendLogEntry): DisplayLogEntry {
  return {
    timestamp: entry.timestamp,
    level: entry.level,
    source: entry.source,
    message: entry.message,
    logger: entry.component,
    data: {
      ...entry.extra,
      url: entry.url,
      user_agent: entry.userAgent,
    },
  }
}

function normalizeBackendLog(entry: SystemLogEntry): DisplayLogEntry {
  return {
    timestamp: entry.timestamp || '',
    level: entry.level,
    source: entry.source,
    message: entry.message,
    logger: entry.logger,
    request_id: entry.request_id,
    data: entry.data,
  }
}

function entryKey(entry: DisplayLogEntry) {
  return [
    entry.timestamp,
    entry.level,
    entry.source,
    entry.logger || '',
    entry.message,
    entry.request_id || '',
  ].join('|')
}

function levelBadgeClasses(level: string) {
  switch (level) {
    case 'error':
      return 'bg-red-100 text-red-700 border-red-200'
    case 'warn':
    case 'warning':
      return 'bg-amber-100 text-amber-800 border-amber-200'
    case 'debug':
      return 'bg-slate-100 text-slate-700 border-slate-200'
    default:
      return 'bg-blue-100 text-blue-700 border-blue-200'
  }
}

export function LogsPage() {
  const [level, setLevel] = useState<LevelFilter>('all')
  const [source, setSource] = useState<SourceFilter>('all')
  const [search, setSearch] = useState('')
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [liveEntries, setLiveEntries] = useState<DisplayLogEntry[]>([])

  const handleSocketOpen = useCallback(() => undefined, [])
  const handleSocketMessage = useCallback((event: MessageEvent) => {
    try {
      const payload = JSON.parse(event.data)
      if (payload?.type !== 'log.entry' || !payload?.data) {
        return
      }

      setLiveEntries((current) => [normalizeBackendLog(payload.data as SystemLogEntry), ...current].slice(0, 200))
    } catch {
      logger.warn('LogsPage', 'Failed to parse log stream event')
    }
  }, [])

  const backendLogsQuery = useQuery({
    queryKey: ['system-logs', level, source, search],
    queryFn: () =>
      systemApi.getLogs({
        level: level === 'all' ? undefined : level,
        source: source === 'all' ? undefined : source,
        search: search || undefined,
        limit: 200,
      }),
    refetchInterval: autoRefresh ? 5000 : false,
  })

  const statusQuery = useQuery<SystemStatus>({
    queryKey: ['system-status'],
    queryFn: systemApi.getStatus,
    refetchInterval: autoRefresh ? 5000 : false,
  })

  useEffect(() => {
    setLiveEntries(logger.getEntries().map(normalizeFrontendLog))
    return logger.subscribe((entry) => {
      setLiveEntries((current) => [normalizeFrontendLog(entry), ...current].slice(0, 200))
    })
  }, [])

  useWebSocket(LOG_WS_URL, {
    onOpen: handleSocketOpen,
    onMessage: handleSocketMessage,
  })

  const logs = useMemo(() => {
    const backendEntries = (backendLogsQuery.data?.logs || []).map(normalizeBackendLog)
    const frontendEntries = logger.getEntries().map(normalizeFrontendLog)
    const merged = [...liveEntries, ...backendEntries, ...frontendEntries]

    const deduped = new Map<string, DisplayLogEntry>()
    for (const entry of merged) {
      if (!deduped.has(entryKey(entry))) {
        deduped.set(entryKey(entry), entry)
      }
    }

    return [...deduped.values()]
      .filter((entry) => (level === 'all' ? true : entry.level === level))
      .filter((entry) => (source === 'all' ? true : entry.source === source))
      .filter((entry) => {
        if (!search) {
          return true
        }
        return JSON.stringify(entry).toLowerCase().includes(search.toLowerCase())
      })
      .sort((a, b) => b.timestamp.localeCompare(a.timestamp))
      .slice(0, 200)
  }, [backendLogsQuery.data?.logs, level, liveEntries, search, source])

  const exportLogs = () => {
    const blob = new Blob([JSON.stringify(logs, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `knowledge-os-logs-${new Date().toISOString()}.json`
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="mx-auto flex h-full max-w-7xl flex-col gap-6 px-4 py-6 sm:px-6 sm:py-8">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold">
            <ScrollText className="h-6 w-6" />
            Logs
          </h1>
          <p className="mt-1 text-muted-foreground">Backend and frontend application logs in one view.</p>
        </div>
        <Button variant="outline" onClick={exportLogs}>
          <Download className="mr-2 h-4 w-4" />
          Export JSON
        </Button>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Backend Version</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            {statusQuery.data?.version || 'Unavailable'}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Requests / Errors</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            {statusQuery.data ? `${statusQuery.data.request_counts.total} / ${statusQuery.data.error_counts.total}` : 'Unavailable'}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Active WebSockets</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            {statusQuery.data?.active_websocket_connections.total ?? 'Unavailable'}
          </CardContent>
        </Card>
      </div>

      <Card className="flex min-h-0 flex-1 flex-col">
        <CardHeader className="gap-4">
          <div className="grid gap-4 md:grid-cols-4">
            <div className="space-y-2">
              <Label htmlFor="log-level">Level</Label>
              <Select value={level} onValueChange={(value) => setLevel(value as LevelFilter)}>
                <SelectTrigger id="log-level">
                  <SelectValue placeholder="All levels" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="debug">Debug</SelectItem>
                  <SelectItem value="info">Info</SelectItem>
                  <SelectItem value="warn">Warn</SelectItem>
                  <SelectItem value="error">Error</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="log-source">Source</Label>
              <Select value={source} onValueChange={(value) => setSource(value as SourceFilter)}>
                <SelectTrigger id="log-source">
                  <SelectValue placeholder="All sources" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="backend">Backend</SelectItem>
                  <SelectItem value="frontend">Frontend</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="log-search">Search</Label>
              <Input
                id="log-search"
                placeholder="Message, logger, request ID"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>
          </div>

          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(event) => setAutoRefresh(event.target.checked)}
            />
            Auto-refresh every 5 seconds
          </label>
        </CardHeader>

        <CardContent className="min-h-0 flex-1 overflow-auto">
          {backendLogsQuery.isError && !backendLogsQuery.data ? (
            <QueryError message="Failed to load backend logs" onRetry={() => backendLogsQuery.refetch()} />
          ) : backendLogsQuery.isLoading && !backendLogsQuery.data ? (
            <div className="flex h-40 items-center justify-center">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className="border-b text-xs uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th className="px-3 py-3 font-medium">Timestamp</th>
                    <th className="px-3 py-3 font-medium">Level</th>
                    <th className="px-3 py-3 font-medium">Source</th>
                    <th className="px-3 py-3 font-medium">Message</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((entry) => (
                    <tr key={entryKey(entry)} className="border-b align-top">
                      <td className="px-3 py-3 text-muted-foreground">{entry.timestamp || 'Unknown'}</td>
                      <td className="px-3 py-3">
                        <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${levelBadgeClasses(entry.level)}`}>
                          {entry.level}
                        </span>
                      </td>
                      <td className="px-3 py-3 text-muted-foreground">{entry.source}</td>
                      <td className="px-3 py-3">
                        <div className="font-medium">{entry.message}</div>
                        {(entry.logger || entry.request_id) && (
                          <div className="mt-1 text-xs text-muted-foreground">
                            {[entry.logger, entry.request_id].filter(Boolean).join(' • ')}
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {logs.length === 0 && (
                <div className="py-10 text-center text-sm text-muted-foreground">No logs match the current filters.</div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
