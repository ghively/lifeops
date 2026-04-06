import { useQueryErrorResetBoundary } from '@tanstack/react-query'
import { AlertTriangle, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface QueryErrorProps {
  message?: string
  onRetry?: () => void
}

/**
 * Reusable error display for React Query errors. Renders an alert with retry button.
 * Usage: {query.isError && <QueryError message="..." onRetry={() => query.refetch()} />}
 */
export function QueryError({ message, onRetry }: QueryErrorProps) {
  const { reset } = useQueryErrorResetBoundary()

  return (
    <div className="flex flex-col items-center justify-center gap-4 rounded-lg border border-red-200 bg-red-50 p-8 text-center dark:border-red-900 dark:bg-red-950/30">
      <AlertTriangle className="h-8 w-8 text-red-500" />
      <div>
        <p className="font-medium text-red-700 dark:text-red-400">Something went wrong</p>
        <p className="mt-1 text-sm text-red-600 dark:text-red-500">
          {message || 'Failed to load data. Please try again.'}
        </p>
      </div>
      <Button
        variant="outline"
        size="sm"
        onClick={() => {
          reset()
          onRetry?.()
        }}
      >
        <RefreshCw className="mr-2 h-4 w-4" />
        Retry
      </Button>
    </div>
  )
}
