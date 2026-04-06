import { useToast } from '@/hooks/useToast'
import { X } from 'lucide-react'

export function Toaster() {
  const { toasts, dismiss } = useToast()

  if (toasts.length === 0) return null

  return (
    <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 max-w-sm">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`rounded-lg border px-4 py-3 shadow-lg text-sm flex items-start gap-3 animate-in slide-in-from-right-full ${
            t.variant === 'destructive'
              ? 'border-red-200 bg-red-50 text-red-900 dark:bg-red-900/20 dark:text-red-100'
              : 'border bg-background text-foreground'
          }`}
        >
          <div className="flex-1">
            <div className="font-medium">{t.title}</div>
            {t.description && (
              <div className="mt-1 opacity-80">{t.description}</div>
            )}
          </div>
          <button
            type="button"
            onClick={() => dismiss(t.id)}
            className="shrink-0 opacity-50 hover:opacity-100"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      ))}
    </div>
  )
}
