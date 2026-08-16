import { useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { agentsApi, type AgentItem } from '@/services/api'

type AgentSnapshot = Pick<AgentItem, 'status' | 'current_task' | 'current_action'>

const BUSY_STATUSES = new Set<AgentItem['status']>(['active', 'busy', 'working'])

export function useAgentNotifications(enabled: boolean) {
  const previousAgentsRef = useRef<Record<string, AgentSnapshot>>({})

  const { data } = useQuery({
    queryKey: ['agent-notifications'],
    queryFn: agentsApi.list,
    enabled,
    refetchInterval: 10000,
  })

  useEffect(() => {
    if (!enabled || Notification.permission !== 'granted') {
      return
    }

    const currentAgents = data?.agents ?? []
    const previousAgents = previousAgentsRef.current

    for (const agent of currentAgents) {
      const previous = previousAgents[agent.id]
      if (!previous) {
        continue
      }

      const statusChanged = previous.status !== agent.status
      const taskChanged = previous.current_task !== agent.current_task && !!agent.current_task

      if (!statusChanged && !taskChanged) {
        continue
      }

      const title = `Agent update: @${agent.name}`
      const body = taskChanged
        ? agent.current_task
        : BUSY_STATUSES.has(agent.status)
        ? `Status changed to ${agent.status}.`
        : `Agent is now ${agent.status}.`

      if ('serviceWorker' in navigator) {
        navigator.serviceWorker.ready
          .then((registration) =>
            registration.showNotification(title, {
              body,
              tag: `agent-${agent.id}`,
              icon: '/icons/pwa-192x192.png',
              badge: '/icons/pwa-192x192.png',
              data: { agentId: agent.id },
            }),
          )
          .catch(() => {
            new Notification(title, { body, tag: `agent-${agent.id}` })
          })
      } else {
        new Notification(title, { body, tag: `agent-${agent.id}` })
      }
    }

    previousAgentsRef.current = currentAgents.reduce<Record<string, AgentSnapshot>>((acc, agent) => {
      acc[agent.id] = {
        status: agent.status,
        current_task: agent.current_task,
        current_action: agent.current_action,
      }
      return acc
    }, {})
  }, [data?.agents, enabled])
}
