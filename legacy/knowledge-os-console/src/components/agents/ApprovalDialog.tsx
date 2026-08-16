import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import type { AgentApprovalRequest } from '@/services/api'

interface ApprovalDialogProps {
  approval: AgentApprovalRequest | null
  open: boolean
  onDecision: (approved: boolean) => void
}

export function ApprovalDialog({ approval, open, onDecision }: ApprovalDialogProps) {
  const [remaining, setRemaining] = useState(approval?.timeout_seconds || 60)

  useEffect(() => {
    setRemaining(approval?.timeout_seconds || 60)
  }, [approval?.request_id, approval?.timeout_seconds])

  useEffect(() => {
    if (!open || !approval) {
      return
    }
    const interval = window.setInterval(() => {
      setRemaining((current) => {
        if (current <= 1) {
          window.clearInterval(interval)
          onDecision(false)
          return 0
        }
        return current - 1
      })
    }, 1000)
    return () => window.clearInterval(interval)
  }, [approval, onDecision, open])

  return (
    <Dialog open={open}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Approve Tool Execution</DialogTitle>
          <DialogDescription>
            {approval?.tool_name || 'Tool'} is requesting a destructive operation. This request expires in {remaining}s.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 text-sm">
          <div>
            <div className="font-medium">Description</div>
            <div className="text-muted-foreground">{approval?.description || 'No description provided.'}</div>
          </div>

          <div>
            <div className="font-medium">Arguments</div>
            <pre className="mt-2 overflow-x-auto rounded-lg border bg-muted p-3 text-xs">
              {JSON.stringify(approval?.arguments || {}, null, 2)}
            </pre>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onDecision(false)}>Reject</Button>
          <Button onClick={() => onDecision(true)}>Approve</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
