import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createEditor, Descendant, Transforms, Editor, Element as SlateElement, BaseEditor, Text, Range, NodeEntry, Node } from 'slate'
import { Slate, Editable, withReact, ReactEditor, RenderLeafProps } from 'slate-react'
import { withHistory } from 'slate-history'
import { createPortal } from 'react-dom'
import {
  Plus,
  CheckSquare,
  Type,
  Heading1,
  List,
  ListOrdered,
  Quote,
  Code,
  ArrowRightToLine,
  ArrowLeftToLine,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { useCollaborativeCursors, broadcastSelection } from '@/components/collaboration/CollaborativeCursors'
import { useCollaborationStore } from '@/stores/collaboration'
import { PresenceIndicator } from '@/components/collaboration/PresenceIndicator'
import type { CursorDecoration } from '@/components/collaboration/CollaborativeCursors'

type BlockType = 'paragraph' | 'heading' | 'todo' | 'bullet' | 'numbered' | 'quote' | 'code'

export interface BlockElement {
  id: string
  type: BlockType
  level?: number
  checked?: boolean
  content?: string
  children: { text: string }[]
}

interface OutlinerEditorProps {
  objectId: string
  initialBlocks?: BlockElement[]
  onChange?: (blocks: BlockElement[]) => void
  readOnly?: boolean
  enableCollaboration?: boolean
}

type CustomElement = {
  id: string
  type: BlockType
  level?: number
  checked?: boolean
  children: CustomText[]
}

type CustomText = {
  text: string
  bold?: boolean
  italic?: boolean
  code?: boolean
  linkType?: 'wiki' | 'block'
  linkValue?: string
}

type DecoratedRange = Range & {
  linkType?: 'wiki' | 'block'
  linkValue?: string
}

declare module 'slate' {
  interface CustomTypes {
    Editor: BaseEditor & ReactEditor
    Element: CustomElement
    Text: CustomText
  }
}

const SLASH_COMMANDS: Record<string, BlockType> = {
  text: 'paragraph',
  p: 'paragraph',
  heading: 'heading',
  h1: 'heading',
  todo: 'todo',
  task: 'todo',
  bullet: 'bullet',
  list: 'bullet',
  numbered: 'numbered',
  quote: 'quote',
  code: 'code',
}

const SLASH_COMMAND_ITEMS: Array<{
  key: string
  type: BlockType
  label: string
  description: string
  icon: typeof Type
}> = [
  {
    key: 'todo',
    type: 'todo',
    label: '/todo',
    description: 'Add a checkbox task item',
    icon: CheckSquare,
  },
  {
    key: 'heading',
    type: 'heading',
    label: '/heading',
    description: 'Turn this block into a heading',
    icon: Heading1,
  },
  {
    key: 'bullet',
    type: 'bullet',
    label: '/bullet',
    description: 'Create a bulleted list item',
    icon: List,
  },
  {
    key: 'numbered',
    type: 'numbered',
    label: '/numbered',
    description: 'Create a numbered list item',
    icon: ListOrdered,
  },
  {
    key: 'quote',
    type: 'quote',
    label: '/quote',
    description: 'Format as a block quote',
    icon: Quote,
  },
  {
    key: 'code',
    type: 'code',
    label: '/code',
    description: 'Format as a code block',
    icon: Code,
  },
  {
    key: 'paragraph',
    type: 'paragraph',
    label: '/paragraph',
    description: 'Switch back to plain text',
    icon: Type,
  },
]

const createBlockId = () => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `block-${Math.random().toString(36).slice(2, 11)}`
}

const createEmptyBlock = (type: BlockType = 'paragraph', level: number = 0): BlockElement => ({
  id: createBlockId(),
  type,
  level,
  children: [{ text: '' }],
})

const renderElementFactory = (
  onTodoToggle?: (element: CustomElement) => void,
) => {
  return (props: { attributes: React.HTMLAttributes<HTMLElement>; children: React.ReactNode; element: CustomElement }) => {
    const { attributes, children, element } = props
    const { type, level = 0, checked } = element

    const baseClasses = cn(
      'py-1 px-2 -mx-2 rounded hover:bg-muted/30 transition-colors',
      level > 0 && 'ml-4'
    )

    switch (type) {
      case 'heading':
        return <h2 {...attributes} className={cn(baseClasses, 'mt-2 text-xl font-semibold')}>{children}</h2>
      case 'todo':
        return (
          <div {...attributes} className={cn(baseClasses, 'flex items-start gap-2')}>
            <input
              type="checkbox"
              checked={checked}
              className="mt-1.5 h-4 w-4 rounded border-gray-300"
              onChange={() => onTodoToggle?.(element)}
            />
            <span className={cn(checked && 'line-through text-muted-foreground')}>{children}</span>
          </div>
        )
      case 'bullet':
        return <ul {...attributes} className={cn(baseClasses, 'ml-6 list-disc')}><li>{children}</li></ul>
      case 'numbered':
        return <ol {...attributes} className={cn(baseClasses, 'ml-6 list-decimal')}><li>{children}</li></ol>
      case 'quote':
        return <blockquote {...attributes} className={cn(baseClasses, 'border-l-4 border-muted-foreground/30 pl-4 italic')}>{children}</blockquote>
      case 'code':
        return <pre {...attributes} className={cn(baseClasses, 'rounded bg-muted p-2 font-mono text-sm')}><code>{children}</code></pre>
      default:
        return <p {...attributes} className={baseClasses}>{children}</p>
    }
  }
}

/**
 * Custom leaf renderer that handles text formatting.
 * Collaborative cursor overlays are rendered via the decorate system.
 */
const renderLeafFactory = (
  onLinkClick?: (type: 'wiki' | 'block', value: string) => void,
) => {
  return (props: RenderLeafProps) => {
    let { children } = props
    const leaf = props.leaf as CustomText

    // Text formatting
    if (leaf.bold) children = <strong>{children}</strong>
    if (leaf.italic) children = <em>{children}</em>
    if (leaf.code) children = <code className="rounded bg-muted px-1">{children}</code>

    // Wiki/block links
    if (leaf.linkType && leaf.linkValue) {
      children = (
        <button
          type="button"
          className={cn(
            'rounded px-1 underline decoration-dotted underline-offset-4',
            leaf.linkType === 'wiki' ? 'bg-sky-100 text-sky-800' : 'bg-amber-100 text-amber-800'
          )}
          contentEditable={false}
          onMouseDown={(event) => {
            event.preventDefault()
            onLinkClick?.(leaf.linkType!, leaf.linkValue!)
          }}
        >
          {children}
        </button>
      )
    }

    // Collaborative selection highlight
    const cursorDec = (leaf as Record<string, unknown>).__collabCursor as CursorDecoration | undefined
    if (cursorDec) {
      return (
        <span {...props.attributes} className="relative">
          <span
            className="absolute inset-0 pointer-events-none rounded-sm"
            style={{ backgroundColor: cursorDec.color + '20' }}
          />
          <span
            className="absolute pointer-events-none"
            style={{
              left: 0,
              top: 0,
              bottom: 0,
              width: '2px',
              backgroundColor: cursorDec.color,
            }}
          >
            <span
              className="absolute left-0 -top-5 px-1 py-0.5 text-[10px] text-white whitespace-nowrap rounded-sm"
              style={{ backgroundColor: cursorDec.color }}
            >
              {cursorDec.userName}
            </span>
          </span>
          {children}
        </span>
      )
    }

    return <span {...props.attributes}>{children}</span>
  }
}

const Toolbar = ({ editor }: { editor: Editor }) => {
  const toggleBlock = (type: BlockType) => {
    const isActive = isBlockActive(editor, type)
    Transforms.setNodes(
      editor,
      { type: isActive ? 'paragraph' : type },
      { match: (node) => SlateElement.isElement(node) && Editor.isBlock(editor, node) }
    )
  }

  const isBlockActive = (currentEditor: Editor, type: string) => {
    const [match] = Editor.nodes(currentEditor, {
      match: (node) => SlateElement.isElement(node) && node.type === type,
    })
    return !!match
  }

  return (
    <div className="flex items-center gap-1 overflow-x-auto border-b bg-muted/50 p-2">
      <Button aria-label="Type" title="Type" variant="ghost" size="sm" onClick={() => toggleBlock('paragraph')} className={cn(isBlockActive(editor, 'paragraph') && 'bg-muted')}>
        <Type className="h-4 w-4" />
      </Button>
      <Button aria-label="Heading" title="Heading" variant="ghost" size="sm" onClick={() => toggleBlock('heading')} className={cn(isBlockActive(editor, 'heading') && 'bg-muted')}>
        <Heading1 className="h-4 w-4" />
      </Button>
      <Button aria-label="Todo" title="Todo" variant="ghost" size="sm" onClick={() => toggleBlock('todo')} className={cn(isBlockActive(editor, 'todo') && 'bg-muted')}>
        <CheckSquare className="h-4 w-4" />
      </Button>
      <Button aria-label="List" title="List" variant="ghost" size="sm" onClick={() => toggleBlock('bullet')} className={cn(isBlockActive(editor, 'bullet') && 'bg-muted')}>
        <List className="h-4 w-4" />
      </Button>
      <Button aria-label="Quote" title="Quote" variant="ghost" size="sm" onClick={() => toggleBlock('quote')} className={cn(isBlockActive(editor, 'quote') && 'bg-muted')}>
        <Quote className="h-4 w-4" />
      </Button>
      <Button aria-label="Code" title="Code" variant="ghost" size="sm" onClick={() => toggleBlock('code')} className={cn(isBlockActive(editor, 'code') && 'bg-muted')}>
        <Code className="h-4 w-4" />
      </Button>
    </div>
  )
}

export function OutlinerEditor({
  objectId,
  initialBlocks = [],
  onChange,
  readOnly = false,
  enableCollaboration = false,
}: OutlinerEditorProps) {
  const navigate = useNavigate()
  const editor = useMemo(() => withHistory(withReact(createEditor())), [])
  const editorContainerRef = useRef<HTMLDivElement | null>(null)
  const slashMenuRef = useRef<HTMLDivElement | null>(null)
  const initialSignature = useMemo(() => JSON.stringify(initialBlocks), [initialBlocks])
  const [value, setValue] = useState<Descendant[]>(() => {
    if (initialBlocks.length === 0) {
      return [createEmptyBlock()]
    }
    return initialBlocks.map((block) => ({
      id: block.id,
      type: block.type,
      level: block.level || 0,
      checked: block.checked,
      children: block.children,
    }))
  })

  // Collaboration hooks
  const sendCursor = useCollaborationStore((s) => s.sendCursor)
  const collabStatus = useCollaborationStore((s) => s.status)
  const { decorate: collabDecorate } = useCollaborativeCursors(editor, enableCollaboration ? objectId : undefined)
  const [slashMenuOpen, setSlashMenuOpen] = useState(false)
  const [slashQuery, setSlashQuery] = useState('')
  const [slashTargetPath, setSlashTargetPath] = useState<number[] | null>(null)
  const [slashPosition, setSlashPosition] = useState({ top: 0, left: 0 })
  const [selectedSlashIndex, setSelectedSlashIndex] = useState(0)

  useEffect(() => {
    if (initialBlocks.length === 0) {
      setValue([createEmptyBlock()])
      return
    }
    setValue(initialBlocks.map((block) => ({
      id: block.id,
      type: block.type,
      level: block.level || 0,
      checked: block.checked,
      children: block.children,
    })))
  }, [initialBlocks, initialSignature])

  const closeSlashMenu = useCallback(() => {
    setSlashMenuOpen(false)
    setSlashQuery('')
    setSlashTargetPath(null)
    setSelectedSlashIndex(0)
  }, [])

  const updateSlashMenuPosition = useCallback(() => {
    if (typeof window === 'undefined') {
      return
    }

    const selection = window.getSelection()
    if (!selection || selection.rangeCount === 0) {
      return
    }

    const range = selection.getRangeAt(0).cloneRange()
    let rect = range.getBoundingClientRect()

    if (rect.width === 0 && rect.height === 0) {
      const markerRange = range.cloneRange()
      markerRange.collapse(false)
      rect = markerRange.getBoundingClientRect()
    }

    if (rect.width === 0 && rect.height === 0 && editorContainerRef.current) {
      rect = editorContainerRef.current.getBoundingClientRect()
    }

    setSlashPosition({
      top: rect.bottom + window.scrollY + 8,
      left: rect.left + window.scrollX,
    })
  }, [])

  const filteredSlashCommands = useMemo(() => {
    const normalizedQuery = slashQuery.trim().toLowerCase()
    return SLASH_COMMAND_ITEMS.filter((item) => item.key.includes(normalizedQuery))
  }, [slashQuery])

  useEffect(() => {
    if (!slashMenuOpen) {
      return
    }

    if (filteredSlashCommands.length === 0) {
      setSelectedSlashIndex(0)
      return
    }

    setSelectedSlashIndex((current) => Math.min(current, filteredSlashCommands.length - 1))
  }, [filteredSlashCommands, slashMenuOpen])

  const applySlashCommand = useCallback((type: BlockType, targetPath?: number[]) => {
    const path = targetPath ?? slashTargetPath
    if (!path) {
      return
    }

    const text = Editor.string(editor, path)
    const textPath = path.concat(0)

    Transforms.setNodes(editor, { type }, { at: path })
    Transforms.delete(editor, {
      at: {
        anchor: { path: textPath, offset: 0 },
        focus: { path: textPath, offset: text.length },
      },
    })
    Transforms.select(editor, Editor.start(editor, textPath))
    ReactEditor.focus(editor)
    closeSlashMenu()
  }, [closeSlashMenu, editor, slashTargetPath])

  useEffect(() => {
    if (!slashMenuOpen) {
      return
    }

    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as globalThis.Node | null
      if (target && slashMenuRef.current?.contains(target)) {
        return
      }
      closeSlashMenu()
    }

    const handleViewportUpdate = () => updateSlashMenuPosition()

    document.addEventListener('mousedown', handlePointerDown)
    window.addEventListener('resize', handleViewportUpdate)
    window.addEventListener('scroll', handleViewportUpdate, true)

    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
      window.removeEventListener('resize', handleViewportUpdate)
      window.removeEventListener('scroll', handleViewportUpdate, true)
    }
  }, [closeSlashMenu, slashMenuOpen, updateSlashMenuPosition])

  const handleLinkClick = useCallback((type: 'wiki' | 'block', linkValue: string) => {
    if (type === 'block') {
      navigate(`/object/${objectId}?block=${encodeURIComponent(linkValue)}`)
      return
    }
    navigate(`/search?q=${encodeURIComponent(linkValue)}`)
  }, [navigate, objectId])

  const handleTodoToggle = useCallback((element: CustomElement) => {
    const [match] = Editor.nodes(editor, {
      at: [],
      match: (node) => SlateElement.isElement(node) && (node as CustomElement).id === element.id,
      mode: 'all',
    })

    if (!match) {
      return
    }

    const [, path] = match
    Transforms.setNodes(editor, { checked: !element.checked }, { at: path })
  }, [editor])

  // Base decorations (wiki links, block refs)
  const baseDecorate = useCallback(([node, path]: NodeEntry<Node>) => {
    const ranges: DecoratedRange[] = []
    if (!Text.isText(node)) {
      return ranges
    }

    const patterns: Array<{ regex: RegExp; type: 'wiki' | 'block' }> = [
      { regex: /\[\[([^[\]]+)\]\]/g, type: 'wiki' },
      { regex: /\(\(([a-zA-Z0-9-]+)\)\)/g, type: 'block' },
    ]

    for (const pattern of patterns) {
      for (const match of node.text.matchAll(pattern.regex)) {
        if (match.index === undefined) {
          continue
        }
        ranges.push({
          anchor: { path, offset: match.index },
          focus: { path, offset: match.index + match[0].length },
          linkType: pattern.type,
          linkValue: match[1],
        })
      }
    }

    return ranges
  }, [])

  // Combined decorate: base + collaboration cursors
  const decorate = useCallback(
    (entry: NodeEntry<Node>) => {
      const base = baseDecorate(entry)
      if (enableCollaboration) {
        const collab = collabDecorate(entry)
        return [...base, ...collab]
      }
      return base
    },
    [baseDecorate, collabDecorate, enableCollaboration],
  )

  const onKeyDown = useCallback((event: React.KeyboardEvent) => {
    if (readOnly) return

    if (slashMenuOpen) {
      if (event.key === 'ArrowDown') {
        event.preventDefault()
        if (filteredSlashCommands.length > 0) {
          setSelectedSlashIndex((current) => (current + 1) % filteredSlashCommands.length)
        }
        return
      }

      if (event.key === 'ArrowUp') {
        event.preventDefault()
        if (filteredSlashCommands.length > 0) {
          setSelectedSlashIndex((current) => (current - 1 + filteredSlashCommands.length) % filteredSlashCommands.length)
        }
        return
      }

      if (event.key === 'Enter') {
        const selectedCommand = filteredSlashCommands[selectedSlashIndex]
        if (selectedCommand) {
          event.preventDefault()
          applySlashCommand(selectedCommand.type)
          return
        }
      }

      if (event.key === 'Escape') {
        event.preventDefault()
        closeSlashMenu()
        return
      }
    }

    if (event.key === ' ') {
      const [match] = Editor.nodes(editor, {
        match: (node) => SlateElement.isElement(node) && Editor.isBlock(editor, node),
        mode: 'lowest',
      })
      if (match) {
        const [, path] = match
        const text = Editor.string(editor, path).trim()
        const nextType = text.startsWith('/') ? SLASH_COMMANDS[text.slice(1).toLowerCase()] : undefined
        if (nextType) {
          event.preventDefault()
          applySlashCommand(nextType, path)
          return
        }
      }
    }

    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      const [match] = Editor.nodes(editor, {
        match: (node) => SlateElement.isElement(node) && Editor.isBlock(editor, node),
        mode: 'lowest',
      })
      if (match) {
        const [node, path] = match
        const currentType = (node as CustomElement).type
        const currentLevel = (node as CustomElement).level || 0
        Transforms.insertNodes(
          editor,
          createEmptyBlock(currentType === 'heading' ? 'paragraph' : currentType, currentLevel),
          { at: Editor.after(editor, path) }
        )
      }
    }

    if (event.key === 'Tab' && !event.shiftKey) {
      event.preventDefault()
      const [match] = Editor.nodes(editor, {
        match: (node) => SlateElement.isElement(node) && Editor.isBlock(editor, node),
      })
      if (match) {
        const [node, path] = match
        const currentLevel = (node as CustomElement).level || 0
        Transforms.setNodes(editor, { level: Math.min(currentLevel + 1, 6) }, { at: path })
      }
    }

    if (event.key === 'Tab' && event.shiftKey) {
      event.preventDefault()
      const [match] = Editor.nodes(editor, {
        match: (node) => SlateElement.isElement(node) && Editor.isBlock(editor, node),
      })
      if (match) {
        const [node, path] = match
        const currentLevel = (node as CustomElement).level || 0
        Transforms.setNodes(editor, { level: Math.max(currentLevel - 1, 0) }, { at: path })
      }
    }

    if (event.key === 'Backspace') {
      const { selection } = editor
      if (selection && Editor.isStart(editor, selection.anchor, selection.anchor.path)) {
        const [match] = Editor.nodes(editor, {
          match: (node) => SlateElement.isElement(node) && Editor.isBlock(editor, node),
        })
        if (match) {
          const text = Editor.string(editor, match[1])
          if (text === '' && value.length > 1) {
            event.preventDefault()
            Transforms.removeNodes(editor, { at: match[1] })
          }
        }
      }
    }
  }, [
    applySlashCommand,
    closeSlashMenu,
    editor,
    filteredSlashCommands,
    readOnly,
    selectedSlashIndex,
    slashMenuOpen,
    value.length,
  ])

  const handleChange = useCallback((newValue: Descendant[]) => {
    setValue(newValue)

    const { selection } = editor
    if (!readOnly && selection && Range.isCollapsed(selection)) {
      const [match] = Editor.nodes(editor, {
        at: selection,
        match: (node) => SlateElement.isElement(node) && Editor.isBlock(editor, node),
        mode: 'lowest',
      })

      if (match) {
        const [, path] = match
        const text = Editor.string(editor, path)
        const slashMatch = text.match(/^\/([^\s]*)$/)

        if (slashMatch) {
          setSlashMenuOpen(true)
          setSlashQuery(slashMatch[1])
          setSlashTargetPath(path)
          updateSlashMenuPosition()
        } else if (slashMenuOpen) {
          closeSlashMenu()
        }
      } else if (slashMenuOpen) {
        closeSlashMenu()
      }
    } else if (slashMenuOpen) {
      closeSlashMenu()
    }

    // Broadcast cursor to collaborators
    if (enableCollaboration) {
      broadcastSelection(editor, editor.selection, sendCursor)
    }

    const blocks = newValue.map((node) => ({
      id: (node as CustomElement).id || createBlockId(),
      type: (node as CustomElement).type,
      level: (node as CustomElement).level || 0,
      checked: (node as CustomElement).checked,
      content: (node as CustomElement).children.map((child) => child.text).join(''),
      children: (node as CustomElement).children,
    })) as BlockElement[]

    onChange?.(blocks)
  }, [closeSlashMenu, editor, enableCollaboration, onChange, readOnly, sendCursor, slashMenuOpen, updateSlashMenuPosition])

  const addBlock = useCallback(() => {
    if (readOnly) return

    const lastBlock = value[value.length - 1] as CustomElement
    const newBlock = createEmptyBlock('paragraph', lastBlock?.level || 0)
    Transforms.insertNodes(editor, newBlock as Descendant, { at: [value.length] })
  }, [editor, readOnly, value.length])

  const adjustBlockLevel = useCallback((direction: 'in' | 'out') => {
    const [match] = Editor.nodes(editor, {
      match: (node) => SlateElement.isElement(node) && Editor.isBlock(editor, node),
      mode: 'lowest',
    })

    if (!match) {
      return
    }

    const [node, path] = match
    const currentLevel = (node as CustomElement).level || 0
    const nextLevel = direction === 'in'
      ? Math.min(currentLevel + 1, 6)
      : Math.max(currentLevel - 1, 0)

    Transforms.setNodes(editor, { level: nextLevel }, { at: path })
  }, [editor])

  // Leaf renderer with collaboration support
  const renderLeaf = useMemo(
    () => renderLeafFactory(handleLinkClick),
    [handleLinkClick],
  )
  const renderElement = useMemo(
    () => renderElementFactory(handleTodoToggle),
    [handleTodoToggle],
  )

  return (
    <div className="outliner-editor relative">
      {!readOnly && <Toolbar editor={editor} />}

      {/* Presence indicator — shows active collaborators */}
      {enableCollaboration && (
        <div className="flex justify-end mb-2">
          <PresenceIndicator />
        </div>
      )}

      <div ref={editorContainerRef} className="py-4 pb-24 sm:pb-4">
        <Slate editor={editor} initialValue={value} onChange={handleChange}>
          {!readOnly && (
            <div className="mb-3 flex gap-2 overflow-x-auto sm:hidden">
              <Button variant="outline" size="sm" className="min-h-11 min-w-11 touch-manipulation" onClick={() => adjustBlockLevel('out')}>
                <ArrowLeftToLine className="h-4 w-4" />
              </Button>
              <Button variant="outline" size="sm" className="min-h-11 min-w-11 touch-manipulation" onClick={() => adjustBlockLevel('in')}>
                <ArrowRightToLine className="h-4 w-4" />
              </Button>
              <Button variant="outline" size="sm" className="min-h-11 touch-manipulation" onClick={addBlock}>
                <Plus className="mr-2 h-4 w-4" />
                New block
              </Button>
            </div>
          )}
          <Editable
            renderElement={renderElement}
            renderLeaf={renderLeaf}
            decorate={decorate}
            onKeyDown={onKeyDown}
            placeholder="Type something... Use /todo, /heading, [[Wiki Links]], or ((block-id))"
            readOnly={readOnly}
            className="min-h-[200px] touch-manipulation outline-none"
            aria-label="Outliner editor"
          />
        </Slate>

        {slashMenuOpen && filteredSlashCommands.length > 0 && typeof document !== 'undefined' && createPortal(
          <div
            ref={slashMenuRef}
            className="z-50 min-w-[280px] overflow-hidden rounded-lg border bg-card p-1 text-card-foreground shadow-md"
            style={{
              position: 'absolute',
              top: slashPosition.top,
              left: slashPosition.left,
            }}
          >
            {filteredSlashCommands.map((item, index) => {
              const Icon = item.icon
              return (
                <button
                  key={item.key}
                  type="button"
                  className={cn(
                    'flex w-full items-start gap-3 rounded-md px-3 py-2 text-left transition-colors',
                    index === selectedSlashIndex ? 'bg-muted' : 'hover:bg-muted/60'
                  )}
                  onMouseDown={(event) => {
                    event.preventDefault()
                    applySlashCommand(item.type)
                  }}
                >
                  <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                  <span className="flex min-w-0 flex-col">
                    <span className="text-sm font-medium">{item.label}</span>
                    <span className="text-xs text-muted-foreground">{item.description}</span>
                  </span>
                </button>
              )
            })}
          </div>,
          document.body
        )}

        {!readOnly && (
          <Button variant="ghost" className="mt-2 w-full justify-start gap-2 text-muted-foreground" onClick={addBlock}>
            <Plus className="h-4 w-4" />
            Add a block
          </Button>
        )}
      </div>
    </div>
  )
}

export default OutlinerEditor
