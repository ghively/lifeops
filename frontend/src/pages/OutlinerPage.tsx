import { useState, useCallback, useEffect, useMemo, useRef } from 'react'
import ErrorBoundary from '@/components/ErrorBoundary'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus,
  MoreHorizontal,
  ChevronLeft,
  Share,
  Calendar,
  Tag,
  User,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { OutlinerEditor, type BlockElement } from '@/components/outliner/OutlinerEditor'
import { objectsApi, blocksApi, type BlockItem } from '@/services/api'
import { useCollaborationStore } from '@/stores/collaboration'
import { useAuthStore } from '@/stores/auth'
import { cn } from '@/lib/utils'

interface ObjectData {
  id: string
  type: string
  title: string
  icon?: string
  content?: string
  properties: {
    tags?: string[]
    created_at?: string
    updated_at?: string
    status?: string
    priority?: string
    assigned_to?: string
    due_date?: string
  }
  layout: string
}

export function OutlinerPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [isEditing, setIsEditing] = useState(false)
  const [editedTitle, setEditedTitle] = useState('')
  const [pendingBlocks, setPendingBlocks] = useState<BlockElement[] | null>(null)
  const hasLoadedBlocksRef = useRef(false)

  // Collaboration and auth
  const { user } = useAuthStore()
  const { connect: connectCollaboration, disconnect: disconnectCollaboration } = useCollaborationStore()

  // Fetch object data
  const { data: objectData, isLoading: objectLoading } = useQuery({
    queryKey: ['object', id],
    queryFn: () => id ? objectsApi.get(id) : Promise.resolve(null),
    enabled: !!id,
  })

  // Fetch blocks
  const { data: blocksData, isLoading: blocksLoading } = useQuery({
    queryKey: ['blocks', id],
    queryFn: () => {
      if (!id) {
        return Promise.resolve({ blocks: [] as BlockItem[] })
      }
      return blocksApi.getForObject(id)
    },
    enabled: !!id,
  })
  const blocks = blocksData?.blocks ?? []

  useEffect(() => {
    if (id) {
      hasLoadedBlocksRef.current = true
    }
  }, [blocks, id])

  // Connect to collaboration when viewing a document
  useEffect(() => {
    if (!id || !user) return

    // Connect to collaboration room
    connectCollaboration(
      id,
      user.id,
      user.display_name || user.username,
    )

    // Disconnect on unmount
    return () => {
      disconnectCollaboration()
    }
  }, [id, user, connectCollaboration, disconnectCollaboration])

  // Create object mutation
  const createObjectMutation = useMutation({
    mutationFn: objectsApi.create,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['objects'] })
      navigate(`/object/${data.id}`)
    },
  })

  // Update object mutation
  const updateObjectMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<ObjectData> }) =>
      objectsApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['object', id] })
    },
  })

  const saveBlocksMutation = useMutation({
    mutationFn: async (nextBlocks: BlockElement[]) => {
      if (!id) return
      await blocksApi.syncForObject(id, nextBlocks.map((block, order) => ({
        id: block.id,
        content: block.content ?? '',
        type: block.type,
        level: block.level ?? 0,
        order,
        parent_id: null,
        properties: block.type === 'todo' ? { checked: block.checked ?? false } : {},
      })))
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['blocks', id] })
    },
  })

  // Create block mutation
  // Handle title edit
  const handleTitleSave = useCallback(() => {
    if (id && editedTitle !== objectData?.title) {
      updateObjectMutation.mutate({ id, data: { title: editedTitle } })
    }
    setIsEditing(false)
  }, [id, editedTitle, objectData?.title, updateObjectMutation])

  // Handle blocks change
  const handleBlocksChange = useCallback((newBlocks: BlockElement[]) => {
    if (!hasLoadedBlocksRef.current) {
      return
    }
    setPendingBlocks(newBlocks)
  }, [])

  useEffect(() => {
    if (!id || !pendingBlocks) {
      return
    }

    const timer = window.setTimeout(() => {
      saveBlocksMutation.mutate(pendingBlocks)
    }, 400)

    return () => window.clearTimeout(timer)
  }, [id, pendingBlocks, saveBlocksMutation])

  // Create new page
  const handleCreatePage = useCallback(() => {
    createObjectMutation.mutate({
      type: 'page',
      title: 'New Page',
      content: '',
      properties: {},
    })
  }, [createObjectMutation])

  // Loading state
  if (objectLoading || blocksLoading) {
    return (
      <div className="max-w-4xl mx-auto py-8 px-6">
        <div className="animate-pulse">
          <div className="h-8 bg-muted rounded w-1/3 mb-4" />
          <div className="h-4 bg-muted rounded w-1/4 mb-8" />
          <div className="space-y-2">
            <div className="h-6 bg-muted rounded" />
            <div className="h-6 bg-muted rounded" />
            <div className="h-6 bg-muted rounded" />
          </div>
        </div>
      </div>
    )
  }

  // No object selected - show welcome
  if (!id) {
    return (
      <div className="max-w-4xl mx-auto py-8 px-6">
        <div className="text-center py-20">
          <div className="text-6xl mb-4">📝</div>
          <h1 className="text-3xl font-bold mb-4">Welcome to Knowledge OS</h1>
          <p className="text-muted-foreground mb-8 max-w-md mx-auto">
            Your personal knowledge management system with AI agent integration.
            Create notes, assign tasks to agents, and index your files.
          </p>
          <Button onClick={handleCreatePage}>
            <Plus className="h-4 w-4 mr-2" />
            Create Your First Page
          </Button>
        </div>
      </div>
    )
  }

  const object = objectData as ObjectData
  const objectType = object?.type || 'page'
  const icon = object?.icon || (objectType === 'task' ? '✅' : objectType === 'agent' ? '🤖' : '📄')
  const editorBlocks = useMemo(() => (
    blocks.map((b: BlockItem) => ({
      id: b.id,
      type: (b.type as BlockElement['type']) || 'paragraph',
      content: b.content,
      level: b.level || 0,
      checked: Boolean(b.properties?.checked),
      children: [{ text: b.content }],
    }))
  ), [blocks])

  return (
    <ErrorBoundary>
    <div className="max-w-4xl mx-auto py-8 px-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-muted-foreground text-sm mb-4">
        <Button aria-label="Back" variant="ghost" size="sm" onClick={() => navigate('/')}>
          <ChevronLeft className="h-4 w-4 mr-1" />
          Back
        </Button>
        <span>•</span>
        <span className="capitalize">{objectType}</span>
        <span>•</span>
        <span>Last edited {object?.properties?.updated_at ? new Date(object.properties.updated_at).toLocaleDateString() : 'just now'}</span>
      </div>

      {/* Object Header */}
      <div className="mb-6">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            {isEditing ? (
              <input
                type="text"
                value={editedTitle}
                onChange={(e) => setEditedTitle(e.target.value)}
                onBlur={handleTitleSave}
                onKeyDown={(e) => e.key === 'Enter' && handleTitleSave()}
                className="text-3xl font-bold bg-transparent border-b-2 border-primary outline-none w-full"
                autoFocus
              />
            ) : (
              <h1 
                className="text-3xl font-bold flex items-center gap-3 cursor-pointer hover:bg-muted/50 rounded px-2 -mx-2 py-1"
                onClick={() => {
                  setEditedTitle(object?.title || '')
                  setIsEditing(true)
                }}
              >
                <span>{icon}</span>
                {object?.title || 'Untitled'}
              </h1>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Button aria-label="Share" data-testid="share-button" variant="ghost" size="icon">
              <Share className="h-4 w-4" />
            </Button>
            <Button aria-label="More" data-testid="more-button" variant="ghost" size="icon">
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>

      {/* Outliner Editor */}
      <OutlinerEditor
        objectId={id}
        initialBlocks={editorBlocks}
        onChange={handleBlocksChange}
        enableCollaboration={!!id && !!user}
      />

      {/* Properties Panel */}
      <div className="mt-8 pt-6 border-t">
        <h3 className="text-sm font-medium text-muted-foreground mb-3">Properties</h3>
        <div className="space-y-2 text-sm">
          <div className="flex items-center gap-4">
            <span className="text-muted-foreground w-20 flex items-center gap-1">
              <Calendar className="h-3 w-3" />
              Created
            </span>
            <span>{object?.properties?.created_at ? new Date(object.properties.created_at).toLocaleDateString() : 'Unknown'}</span>
          </div>
          
          <div className="flex items-center gap-4">
            <span className="text-muted-foreground w-20 flex items-center gap-1">
              <Tag className="h-3 w-3" />
              Tags
            </span>
            <div className="flex gap-1">
              {object?.properties?.tags?.length ? (
                object.properties.tags.map((tag) => (
                  <span key={tag} className="px-2 py-0.5 bg-muted rounded-full text-xs">
                    #{tag}
                  </span>
                ))
              ) : (
                <span className="text-muted-foreground">No tags</span>
              )}
            </div>
          </div>

          {object?.properties?.assigned_to && (
            <div className="flex items-center gap-4">
              <span className="text-muted-foreground w-20 flex items-center gap-1">
                <User className="h-3 w-3" />
                Assigned
              </span>
              <span>@{object.properties.assigned_to}</span>
            </div>
          )}

          {object?.properties?.status && (
            <div className="flex items-center gap-4">
              <span className="text-muted-foreground w-20">Status</span>
              <span className={cn(
                'px-2 py-0.5 rounded-full text-xs',
                object.properties.status === 'done' && 'bg-green-100 text-green-700',
                object.properties.status === 'in-progress' && 'bg-blue-100 text-blue-700',
                object.properties.status === 'todo' && 'bg-gray-100 text-gray-700',
                object.properties.status === 'blocked' && 'bg-red-100 text-red-700',
              )}>
                {object.properties.status}
              </span>
            </div>
          )}

          {object?.properties?.priority && (
            <div className="flex items-center gap-4">
              <span className="text-muted-foreground w-20">Priority</span>
              <span className={cn(
                'px-2 py-0.5 rounded-full text-xs',
                object.properties.priority === 'urgent' && 'bg-red-100 text-red-700',
                object.properties.priority === 'high' && 'bg-orange-100 text-orange-700',
                object.properties.priority === 'medium' && 'bg-yellow-100 text-yellow-700',
                object.properties.priority === 'low' && 'bg-green-100 text-green-700',
              )}>
                {object.properties.priority}
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
    </ErrorBoundary>
  )
}
