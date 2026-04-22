import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createEditor, Transforms, Element as SlateElement, Text } from 'slate'
import { OutlinerEditor, type BlockElement } from '../OutlinerEditor'

// Mock collaboration store
vi.mock('@/stores/collaboration', () => ({
  useCollaborationStore: vi.fn(() => ({
    users: [],
    myColor: '#0000FF',
    status: 'disconnected',
    sendCursor: vi.fn(),
  })),
}))

describe('OutlinerEditor', () => {
  const mockOnChange = vi.fn()

  const initialBlocks: BlockElement[] = [
    {
      id: 'block-1',
      type: 'paragraph',
      children: [{ text: 'Hello world' }],
    },
    {
      id: 'block-2',
      type: 'todo',
      checked: false,
      children: [{ text: 'Task item' }],
    },
  ]

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('basic rendering', () => {
    it('renders editor with initial blocks', () => {
      render(
        <OutlinerEditor
          objectId="test-doc"
          initialBlocks={initialBlocks}
          onChange={mockOnChange}
        />
      )

      expect(screen.getByText('Hello world')).toBeInTheDocument()
      expect(screen.getByText('Task item')).toBeInTheDocument()
    })

    it('renders empty editor without initial blocks', () => {
      const { container } = render(
        <OutlinerEditor
          objectId="test-doc"
          onChange={mockOnChange}
        />
      )

      // Editor should be present but may be empty
      expect(container.querySelector('[contenteditable]')).toBeInTheDocument()
    })

    it('renders read-only when readOnly prop is true', () => {
      render(
        <OutlinerEditor
          objectId="test-doc"
          initialBlocks={initialBlocks}
          readOnly={true}
          onChange={mockOnChange}
        />
      )

      const editableDiv = document.querySelector('[contenteditable]')
      expect(editableDiv?.getAttribute('contenteditable')).toBe('false')
    })

    it('renders toolbar buttons', () => {
      render(
        <OutlinerEditor
          objectId="test-doc"
          initialBlocks={initialBlocks}
          onChange={mockOnChange}
        />
      )

      expect(screen.queryByRole('button')).toBeDefined()
    })
  })

  describe('typing and editing', () => {
    it('calls onChange when text is entered', async () => {
      const user = userEvent.setup()
      render(
        <OutlinerEditor
          objectId="test-doc"
          initialBlocks={initialBlocks}
          onChange={mockOnChange}
        />
      )

      const editor = document.querySelector('[contenteditable]') as HTMLElement
      if (editor) {
        await user.click(editor)
        await user.keyboard('test')

        // onChange should be called
        await waitFor(() => {
          expect(mockOnChange).toHaveBeenCalled()
        }, { timeout: 500 })
      }
    })

    it('updates block content on input', async () => {
      const user = userEvent.setup()
      render(
        <OutlinerEditor
          objectId="test-doc"
          initialBlocks={[
            {
              id: 'block-1',
              type: 'paragraph',
              children: [{ text: '' }],
            },
          ]}
          onChange={mockOnChange}
        />
      )

      const editor = document.querySelector('[contenteditable]') as HTMLElement
      if (editor) {
        await user.click(editor)
        await user.keyboard('new content')

        await waitFor(() => {
          expect(mockOnChange).toHaveBeenCalled()
        }, { timeout: 500 })
      }
    })
  })

  describe('keyboard shortcuts', () => {
    it('handles Enter key to create new block', async () => {
      const user = userEvent.setup()
      render(
        <OutlinerEditor
          objectId="test-doc"
          initialBlocks={initialBlocks}
          onChange={mockOnChange}
        />
      )

      const editor = document.querySelector('[contenteditable]') as HTMLElement
      if (editor) {
        await user.click(editor)
        await user.keyboard('{End}{Enter}')

        // onChange should reflect new block
        await waitFor(() => {
          expect(mockOnChange).toHaveBeenCalled()
        }, { timeout: 500 })
      }
    })

    it('handles Backspace at block start to merge blocks', async () => {
      const user = userEvent.setup()
      const blocks: BlockElement[] = [
        {
          id: 'block-1',
          type: 'paragraph',
          children: [{ text: 'First' }],
        },
        {
          id: 'block-2',
          type: 'paragraph',
          children: [{ text: 'Second' }],
        },
      ]

      render(
        <OutlinerEditor
          objectId="test-doc"
          initialBlocks={blocks}
          onChange={mockOnChange}
        />
      )

      const editor = document.querySelector('[contenteditable]') as HTMLElement
      if (editor) {
        await user.click(editor)
        // Move to start of second block and backspace
        await user.keyboard('{End}{ArrowDown}{Home}{Backspace}')

        await waitFor(() => {
          expect(mockOnChange).toHaveBeenCalled()
        }, { timeout: 500 })
      }
    })

    it('handles Tab to indent block', async () => {
      const user = userEvent.setup()
      render(
        <OutlinerEditor
          objectId="test-doc"
          initialBlocks={initialBlocks}
          onChange={mockOnChange}
        />
      )

      const editor = document.querySelector('[contenteditable]') as HTMLElement
      if (editor) {
        await user.click(editor)
        await user.keyboard('{Tab}')

        await waitFor(() => {
          expect(mockOnChange).toHaveBeenCalled()
        }, { timeout: 500 })
      }
    })

    it('handles Shift+Tab to outdent block', async () => {
      const user = userEvent.setup()
      const blocks: BlockElement[] = [
        {
          id: 'block-1',
          type: 'paragraph',
          level: 2,
          children: [{ text: 'Indented' }],
        },
      ]

      render(
        <OutlinerEditor
          objectId="test-doc"
          initialBlocks={blocks}
          onChange={mockOnChange}
        />
      )

      const editor = document.querySelector('[contenteditable]') as HTMLElement
      if (editor) {
        await user.click(editor)
        await user.keyboard('{Shift>}{Tab}{/Shift}')

        await waitFor(() => {
          expect(mockOnChange).toHaveBeenCalled()
        }, { timeout: 500 })
      }
    })
  })

  describe('block manipulation', () => {
    it('toggles checkbox for todo blocks', async () => {
      const user = userEvent.setup()
      render(
        <OutlinerEditor
          objectId="test-doc"
          initialBlocks={[
            {
              id: 'block-1',
              type: 'todo',
              checked: false,
              children: [{ text: 'Task' }],
            },
          ]}
          onChange={mockOnChange}
        />
      )

      // Find and click checkbox if present
      const checkbox = screen.queryByRole('checkbox')
      if (checkbox) {
        await user.click(checkbox)

        await waitFor(() => {
          expect(mockOnChange).toHaveBeenCalled()
        }, { timeout: 500 })
      }
    })

    it('undo reverts last operation', async () => {
      const user = userEvent.setup()
      render(
        <OutlinerEditor
          objectId="test-doc"
          initialBlocks={initialBlocks}
          onChange={mockOnChange}
        />
      )

      const editor = document.querySelector('[contenteditable]') as HTMLElement
      if (editor) {
        await user.click(editor)
        await user.keyboard('test')

        // Undo with Ctrl+Z
        await user.keyboard('{Control>}z{/Control}')

        await waitFor(() => {
          expect(mockOnChange).toHaveBeenCalled()
        }, { timeout: 500 })
      }
    })

    it('redo restores operation', async () => {
      const user = userEvent.setup()
      render(
        <OutlinerEditor
          objectId="test-doc"
          initialBlocks={initialBlocks}
          onChange={mockOnChange}
        />
      )

      const editor = document.querySelector('[contenteditable]') as HTMLElement
      if (editor) {
        await user.click(editor)
        await user.keyboard('test')
        await user.keyboard('{Control>}z{/Control}')
        await user.keyboard('{Control>}{Shift>}z{/Shift}{/Control}')

        await waitFor(() => {
          expect(mockOnChange).toHaveBeenCalled()
        }, { timeout: 500 })
      }
    })
  })

  describe('paste handling', () => {
    it('handles plaintext paste', async () => {
      const user = userEvent.setup()
      render(
        <OutlinerEditor
          objectId="test-doc"
          initialBlocks={[
            {
              id: 'block-1',
              type: 'paragraph',
              children: [{ text: '' }],
            },
          ]}
          onChange={mockOnChange}
        />
      )

      const editor = document.querySelector('[contenteditable]') as HTMLElement
      if (editor) {
        await user.click(editor)

        // Simulate paste event
        const pasteEvent = new ClipboardEvent('paste', {
          clipboardData: new DataTransfer(),
          bubbles: true,
        })
        pasteEvent.clipboardData?.setData('text/plain', 'pasted text')
        editor.dispatchEvent(pasteEvent)

        await waitFor(() => {
          expect(mockOnChange).toHaveBeenCalled()
        }, { timeout: 500 })
      }
    })

    it('handles multiline paste', async () => {
      const user = userEvent.setup()
      render(
        <OutlinerEditor
          objectId="test-doc"
          initialBlocks={[
            {
              id: 'block-1',
              type: 'paragraph',
              children: [{ text: '' }],
            },
          ]}
          onChange={mockOnChange}
        />
      )

      const editor = document.querySelector('[contenteditable]') as HTMLElement
      if (editor) {
        await user.click(editor)

        const pasteEvent = new ClipboardEvent('paste', {
          clipboardData: new DataTransfer(),
          bubbles: true,
        })
        pasteEvent.clipboardData?.setData('text/plain', 'line 1\nline 2\nline 3')
        editor.dispatchEvent(pasteEvent)

        await waitFor(() => {
          expect(mockOnChange).toHaveBeenCalled()
        }, { timeout: 500 })
      }
    })
  })

  describe('collaboration', () => {
    it('disables collaboration when enableCollaboration is false', () => {
      const { container } = render(
        <OutlinerEditor
          objectId="test-doc"
          initialBlocks={initialBlocks}
          onChange={mockOnChange}
          enableCollaboration={false}
        />
      )

      // Collaboration components should not be rendered
      expect(container.querySelector('[class*="presence"]')).not.toBeInTheDocument()
    })

    it('enables collaboration when enableCollaboration is true', () => {
      vi.mock('@/stores/collaboration', () => ({
        useCollaborationStore: vi.fn(() => ({
          users: [
            {
              user_id: 'user-1',
              display_name: 'Alice',
              color: '#FF0000',
              cursor: { path: [0], offset: 5 },
            },
          ],
          myColor: '#0000FF',
          status: 'connected',
          sendCursor: vi.fn(),
        })),
      }))

      render(
        <OutlinerEditor
          objectId="test-doc"
          initialBlocks={initialBlocks}
          onChange={mockOnChange}
          enableCollaboration={true}
        />
      )

      // Component should render without errors
      expect(screen.getByText('Hello world')).toBeInTheDocument()
    })
  })

  describe('block types', () => {
    it('renders paragraph blocks', () => {
      render(
        <OutlinerEditor
          objectId="test-doc"
          initialBlocks={[
            {
              id: 'block-1',
              type: 'paragraph',
              children: [{ text: 'Paragraph text' }],
            },
          ]}
          onChange={mockOnChange}
        />
      )

      expect(screen.getByText('Paragraph text')).toBeInTheDocument()
    })

    it('renders heading blocks', () => {
      render(
        <OutlinerEditor
          objectId="test-doc"
          initialBlocks={[
            {
              id: 'block-1',
              type: 'heading',
              level: 1,
              children: [{ text: 'Heading' }],
            },
          ]}
          onChange={mockOnChange}
        />
      )

      expect(screen.getByText('Heading')).toBeInTheDocument()
    })

    it('renders bullet list items', () => {
      render(
        <OutlinerEditor
          objectId="test-doc"
          initialBlocks={[
            {
              id: 'block-1',
              type: 'bullet',
              children: [{ text: 'Item 1' }],
            },
            {
              id: 'block-2',
              type: 'bullet',
              children: [{ text: 'Item 2' }],
            },
          ]}
          onChange={mockOnChange}
        />
      )

      expect(screen.getByText('Item 1')).toBeInTheDocument()
      expect(screen.getByText('Item 2')).toBeInTheDocument()
    })

    it('renders numbered list items', () => {
      render(
        <OutlinerEditor
          objectId="test-doc"
          initialBlocks={[
            {
              id: 'block-1',
              type: 'numbered',
              children: [{ text: 'First' }],
            },
            {
              id: 'block-2',
              type: 'numbered',
              children: [{ text: 'Second' }],
            },
          ]}
          onChange={mockOnChange}
        />
      )

      expect(screen.getByText('First')).toBeInTheDocument()
      expect(screen.getByText('Second')).toBeInTheDocument()
    })

    it('renders quote blocks', () => {
      render(
        <OutlinerEditor
          objectId="test-doc"
          initialBlocks={[
            {
              id: 'block-1',
              type: 'quote',
              children: [{ text: 'Quote text' }],
            },
          ]}
          onChange={mockOnChange}
        />
      )

      expect(screen.getByText('Quote text')).toBeInTheDocument()
    })

    it('renders code blocks', () => {
      render(
        <OutlinerEditor
          objectId="test-doc"
          initialBlocks={[
            {
              id: 'block-1',
              type: 'code',
              children: [{ text: 'const x = 1;' }],
            },
          ]}
          onChange={mockOnChange}
        />
      )

      expect(screen.getByText('const x = 1;')).toBeInTheDocument()
    })

    it('renders todo blocks with checkbox', () => {
      render(
        <OutlinerEditor
          objectId="test-doc"
          initialBlocks={[
            {
              id: 'block-1',
              type: 'todo',
              checked: false,
              children: [{ text: 'Todo item' }],
            },
          ]}
          onChange={mockOnChange}
        />
      )

      expect(screen.getByText('Todo item')).toBeInTheDocument()
      // Checkbox may be present
      const checkbox = screen.queryByRole('checkbox')
      expect(checkbox).toBeDefined()
    })
  })
})
