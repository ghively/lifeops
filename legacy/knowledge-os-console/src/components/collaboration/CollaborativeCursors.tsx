/**
 * CollaborativeCursors — Slate plugin that renders remote user cursors and selections.
 *
 * Uses Slate's `decorate` mechanism to overlay colored cursor/selection
 * decorations from the collaboration store's awareness state.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Editor, Range, Text, NodeEntry, Node, Transforms, Path, Element as SlateElement } from 'slate'
import { ReactEditor } from 'slate-react'
import { useCollaborationStore } from '@/stores/collaboration'
import type { PresenceUser, CursorData, SelectionData } from '@/services/collaboration'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
export interface CursorDecoration extends Range {
  isCollabCursor: true
  userId: string
  userName: string
  color: string
  isSelection?: boolean
}

// ---------------------------------------------------------------------------
// Hook: useCollaborativeCursors
// ---------------------------------------------------------------------------

/**
 * Returns a `decorate` function and cursor overlay data for rendering
 * collaborative cursors and selections in the Slate editor.
 */
export function useCollaborativeCursors(editor: Editor, objectId: string | undefined) {
  const users = useCollaborationStore((s) => s.users)

  const cursorUsers = useMemo(
    () => users.filter((u) => u.cursor || u.selection),
    [users],
  )

  /**
   * Decorate function — called by Slate to determine what visual decorations
   * to apply to the document. We return ranges for each remote user's cursor
   * and selection.
   */
  const decorate = useCallback(
    ([node, path]: NodeEntry<Node>): CursorDecoration[] => {
      const decorations: CursorDecoration[] = []

      if (!Text.isText(node)) return decorations
      if (cursorUsers.length === 0) return decorations

      for (const user of cursorUsers) {
        // Selection highlight
        if (user.selection) {
          const { anchor, focus } = user.selection
          // Check if this text node's path is within the selection
          if (pathIntersectsRange(path, anchor.path, focus.path)) {
            const start = pathsEqual(path, anchor.path) ? anchor.offset : 0
            const end = pathsEqual(path, focus.path) ? focus.offset : node.text.length

            if (start < end) {
              decorations.push({
                anchor: { path, offset: start },
                focus: { path, offset: end },
                isCollabCursor: true,
                userId: user.user_id,
                userName: user.display_name,
                color: user.color,
                isSelection: true,
              })
            }
          }
        }

        // Cursor marker (zero-width range at cursor position)
        if (user.cursor && pathsEqual(path, user.cursor.path)) {
          decorations.push({
            anchor: { path, offset: user.cursor.offset },
            focus: { path, offset: Math.min(user.cursor.offset + 1, node.text.length) },
            isCollabCursor: true,
            userId: user.user_id,
            userName: user.display_name,
            color: user.color,
            isSelection: false,
          })
        }
      }

      return decorations
    },
    [cursorUsers],
  )

  return { decorate, cursorUsers }
}

// ---------------------------------------------------------------------------
// Cursor label rendering helpers
// ---------------------------------------------------------------------------

/**
 * Render a cursor label above a text position. Used as a leaf decoration.
 */
export function CursorLabel({ color, name }: { color: string; name: string }) {
  return (
    <span
      className="absolute -top-5 left-0 rounded-t px-1 text-[10px] leading-tight text-white whitespace-nowrap select-none pointer-events-none"
      style={{ backgroundColor: color }}
    >
      {name}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Hook: useCursorBroadcast — broadcasts local cursor position to others
// ---------------------------------------------------------------------------

export function useCursorBroadcast(editor: Editor, objectId: string | undefined) {
  const sendCursor = useCollaborationStore((s) => s.sendCursor)

  useEffect(() => {
    if (!objectId) return

    const { selection } = editor
    if (!selection) return

    // Broadcast initial cursor
    broadcastSelection(editor, selection, sendCursor)

    // We re-broadcast on every selection change via the editor's onChange
  }, [objectId, sendCursor])
}

/**
 * Call this from the Slate onChange handler to broadcast cursor updates.
 */
export function broadcastSelection(
  editor: Editor,
  selection: Range | null,
  sendCursor: (cursor: CursorData | null, selection: SelectionData | null) => void,
) {
  if (!selection) {
    sendCursor(null, null)
    return
  }

  const cursorData: CursorData = {
    path: selection.anchor.path,
    offset: selection.anchor.offset,
  }

  let selectionData: SelectionData | null = null
  if (!Range.isCollapsed(selection)) {
    selectionData = {
      anchor: { path: selection.anchor.path, offset: selection.anchor.offset },
      focus: { path: selection.focus.path, offset: selection.focus.offset },
    }
  }

  sendCursor(cursorData, selectionData)
}

// ---------------------------------------------------------------------------
// Path helpers
// ---------------------------------------------------------------------------

function pathsEqual(a: number[], b: number[]): boolean {
  if (a.length !== b.length) return false
  return a.every((v, i) => v === b[i])
}

function pathIntersectsRange(path: number[], start: number[], end: number[]): boolean {
  // Check if a text node path is within a selection spanning from start to end.
  // Since Slate paths are arrays of numbers (e.g. [2, 0]), we compare element by element.
  const maxLen = Math.max(path.length, start.length, end.length)
  for (let i = 0; i < maxLen; i++) {
    const p = i < path.length ? path[i] : -1
    const s = i < start.length ? start[i] : -1
    const e = i < end.length ? end[i] : -1
    // If path diverges from both start and end at this level, it's outside
    const minVal = Math.min(s, e)
    const maxVal = Math.max(s, e)
    if (p < minVal || p > maxVal) return false
    if (p > minVal && p < maxVal) return true
    // p equals min or max — continue to next level for tie-breaking
  }
  return true // path exactly equals start or end
}
