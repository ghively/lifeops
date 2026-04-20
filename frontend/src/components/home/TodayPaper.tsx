import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Paperclip, ArrowRight, RefreshCw } from 'lucide-react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  agentsApi,
  objectsApi,
  type AgentItem,
  type ObjectItem,
} from '@/services/api'

interface OutlineRow {
  id: string
  text: string
  done: boolean
  when: string
  who?: string
}

const INITIAL_ROWS: OutlineRow[] = [
  {
    id: 'seed-1',
    text: 'Skim <span class="ref">[[Reading list]]</span> and pull out 3 anchors <span class="tag">#writing</span>',
    done: false,
    when: '11:40',
    who: 'EW',
  },
  {
    id: 'seed-2',
    text: 'Ask <span class="ref">@researcher</span> for counter-examples in past proposals',
    done: false,
    when: '12:01',
  },
  {
    id: 'seed-3',
    text: 'Draft opening paragraph — tone: <em>quietly confident</em>',
    done: false,
    when: '—',
  },
]

function humanizeLastSeen(iso?: string): string {
  if (!iso) return 'just now'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return 'just now'
  const diff = Date.now() - then
  const m = Math.floor(diff / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

function escapeText(raw: string): string {
  return raw
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\[\[([^\]]+)\]\]/g, '<span class="ref">[[$1]]</span>')
    .replace(/@([\w-]+)/g, '<span class="ref">@$1</span>')
    .replace(/(^|\s)(#[\w-]+)/g, '$1<span class="tag">$2</span>')
}

export function TodayPaper({ onCreatePage }: { onCreatePage: () => void }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [rows, setRows] = useState<OutlineRow[]>(INITIAL_ROWS)
  const [composer, setComposer] = useState('')

  const { data: agentsData } = useQuery({
    queryKey: ['agents'],
    queryFn: agentsApi.list,
    refetchInterval: 15000,
  })
  const agents: AgentItem[] = agentsData?.agents ?? []

  const { data: objectsData } = useQuery({
    queryKey: ['objects', { limit: 6 }],
    queryFn: () => objectsApi.list({ limit: 6 }),
  })
  const recentObjects: ObjectItem[] = objectsData?.objects ?? []
  const totalObjects = objectsData?.total ?? recentObjects.length

  const runningAgents = useMemo(
    () =>
      agents.filter((a) =>
        ['active', 'busy', 'working'].includes(a.status as string),
      ),
    [agents],
  )

  const today = new Date()
  const dateLabel = today
    .toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    })
    .toUpperCase()
    .replace(/,/g, ' ·')

  const [autosaveLabel, setAutosaveLabel] = useState('')
  useEffect(() => {
    const update = () => {
      const d = new Date()
      setAutosaveLabel(
        `autosaved ${d.getHours().toString().padStart(2, '0')}:${d
          .getMinutes()
          .toString()
          .padStart(2, '0')}`,
      )
    }
    update()
    const t = window.setInterval(update, 60_000)
    return () => window.clearInterval(t)
  }, [])

  const createObjectMutation = useMutation({
    mutationFn: objectsApi.create,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['objects'] })
      navigate(`/object/${data.id}`)
    },
  })

  const toggleRow = (id: string) =>
    setRows((rs) =>
      rs.map((r) => (r.id === id ? { ...r, done: !r.done } : r)),
    )

  const handleSend = () => {
    const value = composer.trim()
    if (!value) return
    setRows((rs) => [
      {
        id: `user-${Date.now()}`,
        text: escapeText(value),
        done: false,
        when: 'now',
        who: 'EW',
      },
      ...rs,
    ])
    setComposer('')
  }

  return (
    <div
      style={{
        flex: 1,
        minHeight: 0,
        padding: 28,
        display: 'grid',
        position: 'relative',
        height: '100%',
      }}
    >
      {/* Grid backdrop */}
      <svg
        className="kos-graph"
        viewBox="0 0 1200 800"
        preserveAspectRatio="xMidYMid slice"
        aria-hidden="true"
      >
        <defs>
          <pattern id="kos-grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path
              d="M 40 0 L 0 0 0 40"
              fill="none"
              stroke="currentColor"
              strokeWidth="0.5"
              opacity="0.12"
            />
          </pattern>
        </defs>
        <rect
          width="100%"
          height="100%"
          fill="url(#kos-grid)"
          style={{ color: 'var(--sidebar-mute)' }}
        />
      </svg>

      <div className="kos-paper">
        {/* Head */}
        <div className="kos-paper-head">
          <div>
            <div className="kos-paper-title">
              Today — <em>a ruled page</em>
            </div>
            <div
              className="kos-paper-meta"
              style={{ marginTop: 4 }}
            >
              <span>{dateLabel}</span>
            </div>
          </div>
          <div className="kos-paper-meta" style={{ marginLeft: 'auto' }}>
            {runningAgents.length > 0 ? (
              <span className="kos-status-pill">
                <span className="pulse" />
                {runningAgents[0].name} {runningAgents[0].current_action || 'working'}
              </span>
            ) : (
              <span className="kos-status-pill" style={{ opacity: 0.8 }}>
                <span className="pulse" />
                idle
              </span>
            )}
            <span className="sep" />
            <span>{rows.length} blocks</span>
            <span className="sep" />
            <span>{autosaveLabel}</span>
          </div>
        </div>

        {/* Body */}
        <div className="kos-paper-body">
          <div style={{ display: 'grid', gap: 22 }}>
            {/* Stats */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(4, minmax(0, 1fr))',
                gap: 10,
              }}
            >
              <div className="kos-stat">
                <div className="kos-stat-label">Open tasks</div>
                <div className="kos-stat-val">
                  <em>{rows.filter((r) => !r.done).length}</em>
                </div>
                <div className="kos-stat-delta">
                  {rows.filter((r) => r.done).length} done today
                </div>
                <svg
                  className="kos-stat-spark"
                  width="70"
                  height="24"
                  viewBox="0 0 70 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                >
                  <path d="M2 18 L10 14 L18 16 L26 10 L34 12 L42 6 L50 8 L58 4 L68 2" />
                </svg>
              </div>
              <div className="kos-stat">
                <div className="kos-stat-label">Notes indexed</div>
                <div className="kos-stat-val">{totalObjects}</div>
                <div className="kos-stat-delta">
                  {recentObjects.length} recent
                </div>
              </div>
              <div className="kos-stat">
                <div className="kos-stat-label">Agents running</div>
                <div className="kos-stat-val">
                  <em>{runningAgents.length}</em>
                </div>
                <div className="kos-stat-delta">
                  {runningAgents.map((a) => a.name).join(' · ') || 'none'}
                </div>
              </div>
              <div className="kos-stat">
                <div className="kos-stat-label">Agents total</div>
                <div className="kos-stat-val">
                  {agents.length}
                  <span
                    style={{ fontSize: 16, color: 'var(--ink-mute)' }}
                  ></span>
                </div>
                <div className="kos-stat-delta">
                  qdrant · local index
                </div>
              </div>
            </div>

            {/* Two columns */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '1.4fr 1fr',
                gap: 22,
              }}
              className="kos-row2"
            >
              {/* Outline */}
              <div className="kos-card">
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    marginBottom: 12,
                  }}
                >
                  <div className="kos-card-title">
                    Outline — <em>Today</em>
                  </div>
                  <button
                    type="button"
                    className="kos-card-action"
                    onClick={onCreatePage}
                  >
                    + new page
                  </button>
                </div>
                <div
                  style={{ display: 'flex', flexDirection: 'column' }}
                >
                  {rows.map((row) => (
                    <button
                      key={row.id}
                      type="button"
                      className={`kos-out-row ${row.done ? 'done' : ''}`}
                      onClick={() => toggleRow(row.id)}
                      style={{
                        textAlign: 'left',
                        background: 'transparent',
                        border: 0,
                        width: '100%',
                      }}
                    >
                      <div className="kos-out-bullet">
                        {row.done && (
                          <svg
                            width="10"
                            height="10"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="3"
                          >
                            <path d="m5 12 5 5L20 7" />
                          </svg>
                        )}
                      </div>
                      <div
                        className="kos-out-text"
                        dangerouslySetInnerHTML={{ __html: row.text }}
                      />
                      <div className="kos-out-meta">
                        {row.who ? (
                          <div className="kos-mini-av">{row.who}</div>
                        ) : (
                          <span>·</span>
                        )}
                        <span>{row.when}</span>
                      </div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Agents in session */}
              <div className="kos-card">
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    marginBottom: 12,
                  }}
                >
                  <div className="kos-card-title">
                    Agents — <em>in session</em>
                  </div>
                  <button
                    type="button"
                    className="kos-card-action"
                    onClick={() => navigate('/agents')}
                  >
                    view all
                  </button>
                </div>
                <div>
                  {agents.length === 0 ? (
                    <div
                      className="kos-agent-block"
                      style={{ color: 'var(--ink-mute)', fontSize: 13.5 }}
                    >
                      No agents configured yet. Add one from the Agents page.
                    </div>
                  ) : (
                    agents.slice(0, 3).map((agent, i) => {
                      const idle =
                        agent.status === 'idle' ||
                        agent.status === 'offline'
                      return (
                        <button
                          key={agent.id}
                          type="button"
                          className="kos-agent-block"
                          onClick={() =>
                            navigate(
                              `/agents/${encodeURIComponent(agent.name)}/chat`,
                            )
                          }
                          style={{
                            width: '100%',
                            textAlign: 'left',
                            background: 'transparent',
                            border: 0,
                            borderBottom:
                              i < Math.min(agents.length, 3) - 1
                                ? '1px dashed var(--hair)'
                                : 0,
                            cursor: 'pointer',
                          }}
                        >
                          <div
                            className={`kos-agent-av ${idle ? 'gray' : ''}`}
                          >
                            {agent.name.charAt(0).toLowerCase()}
                          </div>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div
                              style={{
                                display: 'flex',
                                alignItems: 'baseline',
                                gap: 8,
                                marginBottom: 4,
                              }}
                            >
                              <div className="kos-agent-name">
                                <em>@{agent.name}</em>
                              </div>
                              <div className="kos-agent-when">
                                · {humanizeLastSeen(agent.last_seen)}
                              </div>
                            </div>
                            <div className="kos-agent-msg">
                              {agent.current_task ||
                                agent.description ||
                                (idle
                                  ? 'idle — waiting for a task'
                                  : 'working on current task')}
                            </div>
                          </div>
                        </button>
                      )
                    })
                  )}
                </div>
              </div>
            </div>

            {/* Recent objects shortcut */}
            {recentObjects.length > 0 && (
              <div className="kos-card">
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    marginBottom: 12,
                  }}
                >
                  <div className="kos-card-title">
                    Recent — <em>open to continue</em>
                  </div>
                  <button
                    type="button"
                    className="kos-card-action"
                    onClick={() =>
                      queryClient.invalidateQueries({ queryKey: ['objects'] })
                    }
                    aria-label="Refresh recent objects"
                  >
                    <RefreshCw size={11} style={{ marginRight: 4 }} />
                    refresh
                  </button>
                </div>
                <div style={{ display: 'grid', gap: 2 }}>
                  {recentObjects.slice(0, 5).map((obj) => (
                    <button
                      key={obj.id}
                      type="button"
                      className="kos-out-row"
                      onClick={() => navigate(`/object/${obj.id}`)}
                      style={{
                        background: 'transparent',
                        border: 0,
                        width: '100%',
                        textAlign: 'left',
                      }}
                    >
                      <div className="kos-mini-av">
                        {obj.icon || (obj.type || 'N').charAt(0).toUpperCase()}
                      </div>
                      <div className="kos-out-text">
                        {obj.title || 'Untitled'}
                      </div>
                      <div className="kos-out-meta">
                        <span>{obj.type}</span>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Composer */}
        <div className="kos-composer">
          <div
            style={{ color: 'var(--ink-mute)' }}
            title="Ask an agent"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.7"
            >
              <path d="M21 12a8 8 0 1 1-3.5-6.6L21 3v6h-6" />
            </svg>
          </div>
          <input
            className="kos-composer-input"
            placeholder="Write a block, /command, or @mention an agent…"
            value={composer}
            onChange={(e) => setComposer(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleSend()
            }}
            aria-label="Composer"
          />
          <button
            type="button"
            className="kos-btn"
            onClick={() =>
              createObjectMutation.mutate({
                type: 'page',
                title: composer.trim() || 'New Page',
                content: '',
                properties: {},
              })
            }
            disabled={createObjectMutation.isPending}
          >
            <Paperclip size={14} />
            New page
          </button>
          <button
            type="button"
            className="kos-btn primary"
            onClick={handleSend}
          >
            Send
            <ArrowRight size={14} />
          </button>
        </div>
      </div>
    </div>
  )
}
