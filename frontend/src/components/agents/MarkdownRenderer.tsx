import { Fragment } from 'react'

import { cn } from '@/lib/utils'

interface MarkdownRendererProps {
  content: string
  className?: string
}

function renderInline(text: string) {
  const parts = text.split(/(`[^`]+`|\[.*?\]\(.*?\))/g)

  return parts.map((part, index) => {
    if (part.startsWith('`') && part.endsWith('`')) {
      return (
        <code key={`${part}-${index}`} className="rounded bg-muted px-1.5 py-0.5 font-mono text-[0.9em]">
          {part.slice(1, -1)}
        </code>
      )
    }

    const linkMatch = part.match(/^\[(.+)\]\((.+)\)$/)
    if (linkMatch) {
      return (
        <a
          key={`${part}-${index}`}
          href={linkMatch[2]}
          target="_blank"
          rel="noreferrer"
          className="text-primary underline underline-offset-4"
        >
          {linkMatch[1]}
        </a>
      )
    }

    return <Fragment key={`${part}-${index}`}>{part}</Fragment>
  })
}

export function MarkdownRenderer({ content, className }: MarkdownRendererProps) {
  const lines = content.replace(/\r\n/g, '\n').split('\n')
  const blocks: React.ReactNode[] = []
  let index = 0

  while (index < lines.length) {
    const line = lines[index]

    if (!line.trim()) {
      index += 1
      continue
    }

    if (line.startsWith('```')) {
      const language = line.slice(3).trim()
      const codeLines: string[] = []
      index += 1

      while (index < lines.length && !lines[index].startsWith('```')) {
        codeLines.push(lines[index])
        index += 1
      }

      index += 1
      blocks.push(
        <pre key={`code-${index}`} className="overflow-x-auto rounded-lg bg-slate-950 p-4 text-sm text-slate-100">
          {language ? <div className="mb-2 text-xs uppercase tracking-[0.2em] text-slate-400">{language}</div> : null}
          <code>{codeLines.join('\n')}</code>
        </pre>
      )
      continue
    }

    const headingMatch = line.match(/^(#{1,3})\s+(.*)$/)
    if (headingMatch) {
      const level = headingMatch[1].length
      const headingClass =
        level === 1
          ? 'text-2xl font-semibold'
          : level === 2
            ? 'text-xl font-semibold'
            : 'text-lg font-semibold'

      blocks.push(
        <div key={`heading-${index}`} className={headingClass}>
          {renderInline(headingMatch[2])}
        </div>
      )
      index += 1
      continue
    }

    if (line.startsWith('- ') || line.startsWith('* ')) {
      const items: string[] = []
      while (index < lines.length && (lines[index].startsWith('- ') || lines[index].startsWith('* '))) {
        items.push(lines[index].slice(2))
        index += 1
      }

      blocks.push(
        <ul key={`list-${index}`} className="list-disc space-y-1 pl-5">
          {items.map((item, itemIndex) => (
            <li key={`${item}-${itemIndex}`}>{renderInline(item)}</li>
          ))}
        </ul>
      )
      continue
    }

    const paragraphLines = [line]
    index += 1
    while (index < lines.length && lines[index].trim() && !lines[index].startsWith('```') && !lines[index].match(/^(#{1,3})\s+/) && !lines[index].startsWith('- ') && !lines[index].startsWith('* ')) {
      paragraphLines.push(lines[index])
      index += 1
    }

    blocks.push(
      <p key={`paragraph-${index}`} className="leading-7">
        {renderInline(paragraphLines.join(' '))}
      </p>
    )
  }

  return <div className={cn('space-y-4 text-sm', className)}>{blocks}</div>
}
