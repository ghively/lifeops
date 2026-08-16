import { useDeferredValue, useMemo, useState } from 'react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { MarkdownRenderer } from './MarkdownRenderer'

export const AGENT_FILE_TABS = ['AGENT.md', 'SOUL.md', 'MEMORY.md', 'TOOLS.md'] as const

export type AgentFileTab = typeof AGENT_FILE_TABS[number]

interface MarkdownEditorProps {
  activeFile: AgentFileTab
  content: string
  isDirty: boolean
  isSaving?: boolean
  onFileChange: (file: AgentFileTab) => void
  onChange: (content: string) => void
  onSave: () => void
  onDiscard: () => void
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function highlightMarkdown(value: string) {
  return escapeHtml(value)
    .replace(/^(#{1,6}\s.*)$/gm, '<span class="text-amber-700 font-semibold">$1</span>')
    .replace(/^(- |\* |\d+\.\s)(.*)$/gm, '<span class="text-sky-700">$1</span>$2')
    .replace(/(`[^`]+`)/g, '<span class="rounded bg-slate-200 px-1 text-fuchsia-700">$1</span>')
    .replace(/(\*\*[^*]+\*\*)/g, '<span class="font-semibold text-emerald-700">$1</span>')
    .replace(/(\[[^\]]+\]\([^)]+\))/g, '<span class="text-blue-700 underline">$1</span>')
}

export function MarkdownEditor({
  activeFile,
  content,
  isDirty,
  isSaving = false,
  onFileChange,
  onChange,
  onSave,
  onDiscard,
}: MarkdownEditorProps) {
  const [previewOpen, setPreviewOpen] = useState(true)
  const deferredContent = useDeferredValue(content)

  const highlightedContent = useMemo(() => {
    const html = highlightMarkdown(deferredContent || '')
    return html ? `${html}<br />` : ''
  }, [deferredContent])

  return (
    <div className="flex h-full min-h-[32rem] flex-col overflow-hidden rounded-lg border bg-card">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
        <div className="flex flex-wrap gap-2">
          {AGENT_FILE_TABS.map((file) => (
            <Button
              key={file}
              variant={file === activeFile ? 'default' : 'outline'}
              size="sm"
              onClick={() => onFileChange(file)}
            >
              {file}
            </Button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => setPreviewOpen((current) => !current)}>
            {previewOpen ? 'Hide Preview' : 'Show Preview'}
          </Button>
          <Button variant="outline" size="sm" onClick={onDiscard} disabled={!isDirty || isSaving}>
            Discard
          </Button>
          <Button size="sm" onClick={onSave} disabled={!isDirty || isSaving}>
            {isSaving ? 'Saving...' : 'Save'}
          </Button>
        </div>
      </div>

      <div className={cn('grid flex-1 min-h-0', previewOpen ? 'lg:grid-cols-2' : 'grid-cols-1')}>
        <div className="min-h-0 border-b lg:border-b-0 lg:border-r">
          <div className="border-b px-4 py-2 text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
            Editor
          </div>
          <div className="relative h-full min-h-[18rem] overflow-auto bg-stone-50">
            <pre
              aria-hidden="true"
              className="pointer-events-none min-h-full whitespace-pre-wrap break-words px-4 py-4 font-mono text-sm leading-6 text-slate-900"
              dangerouslySetInnerHTML={{ __html: highlightedContent }}
            />
            <textarea
              value={content}
              onChange={(event) => onChange(event.target.value)}
              spellCheck={false}
              className="absolute inset-0 h-full w-full resize-none bg-transparent px-4 py-4 font-mono text-sm leading-6 text-transparent caret-slate-900 focus:outline-none"
            />
          </div>
        </div>

        {previewOpen ? (
          <div className="min-h-0 overflow-auto">
            <div className="border-b px-4 py-2 text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
              Preview
            </div>
            <div className="px-4 py-4">
              <MarkdownRenderer content={content} />
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}
