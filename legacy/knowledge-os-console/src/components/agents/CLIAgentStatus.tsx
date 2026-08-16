import { CheckCircle2, XCircle } from 'lucide-react'

import { cn } from '@/lib/utils'
import type { CLIAgentStatus as CLIAgentStatusType } from '@/services/api'

const CLI_AGENT_ORDER = ['codex', 'claude_code', 'kimi', 'gemini', 'opencode']

interface CLIAgentStatusProps {
  status?: CLIAgentStatusType
  className?: string
}

export function CLIAgentStatus({ status, className }: CLIAgentStatusProps) {
  return (
    <div className={cn('flex flex-wrap gap-2', className)}>
      {CLI_AGENT_ORDER.map((name) => {
        const agent = status?.agents?.[name]
        const installed = !!agent?.installed

        return (
          <div
            key={name}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium',
              installed
                ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                : 'border-red-200 bg-red-50 text-red-700'
            )}
            title={agent?.error || agent?.description || name}
          >
            {installed ? <CheckCircle2 className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}
            <span>{name}</span>
          </div>
        )
      })}
    </div>
  )
}
