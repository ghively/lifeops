import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Folder, File, Search, Plus, RefreshCw, Loader2, FileText, Image, Code } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { filesApi, settingsApi, type FileItem } from '@/services/api'
import { cn } from '@/lib/utils'
import { QueryError } from '@/components/QueryError'

const fileTypeIcons: Record<string, React.ElementType> = {
  'text/plain': FileText,
  'text/markdown': FileText,
  'application/pdf': FileText,
  'image/png': Image,
  'image/jpeg': Image,
  'text/x-python': Code,
  'text/javascript': Code,
  'text/typescript': Code,
  'default': File,
}

const fileTypeColors: Record<string, string> = {
  'text/plain': 'text-blue-500',
  'text/markdown': 'text-blue-500',
  'application/pdf': 'text-red-500',
  'image/png': 'text-purple-500',
  'image/jpeg': 'text-purple-500',
  'text/x-python': 'text-green-500',
  'text/javascript': 'text-yellow-500',
  'text/typescript': 'text-blue-500',
  'default': 'text-gray-500',
}

function formatFileSize(bytes?: number): string {
  if (!bytes) return ''
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${sizes[i]}`
}

function getFileIcon(contentType?: string) {
  return fileTypeIcons[contentType || 'default'] || fileTypeIcons.default
}

function getFileColor(contentType?: string) {
  return fileTypeColors[contentType || 'default'] || fileTypeColors.default
}

export function FilesPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | 'indexed' | 'processing' | 'pending' | 'error'>('all')
  const [addFolderOpen, setAddFolderOpen] = useState(false)
  const [newFolderPath, setNewFolderPath] = useState('')
  const [reindexingFileId, setReindexingFileId] = useState<string | null>(null)
  const queryClient = useQueryClient()
  const { data: filesData, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['files'],
    queryFn: filesApi.list,
    refetchInterval: 30000, // Poll every 30 seconds
  })
  const files = (filesData?.files ?? []) as FileItem[]
  const selectedFile = files.find((file) => file.id === searchParams.get('file')) || null

  // Add folder mutation
  const addFolderMutation = useMutation({
    mutationFn: (path: string) => settingsApi.addWatchedFolder(path),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['watched-folders'] })
      queryClient.invalidateQueries({ queryKey: ['files'] })
      setAddFolderOpen(false)
      setNewFolderPath('')
    },
  })

  // Reindex file mutation
  const reindexMutation = useMutation({
    mutationFn: (fileId: string) => filesApi.reindex(fileId),
    onSuccess: () => {
      setReindexingFileId(null)
      queryClient.invalidateQueries({ queryKey: ['files'] })
    },
    onError: () => {
      setReindexingFileId(null)
    },
  })

  const filteredFiles = files.filter((file: FileItem) => {
    const matchesSearch = (
      (file.filename || file.name || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
      file.path.toLowerCase().includes(searchQuery.toLowerCase())
    )
    const matchesStatus = statusFilter === 'all' || file.index_status === statusFilter
    return matchesSearch && matchesStatus
  })

  const handleAddFolder = () => {
    if (newFolderPath.trim()) {
      addFolderMutation.mutate(newFolderPath.trim())
    }
  }

  const handleReindex = (fileId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setReindexingFileId(fileId)
    reindexMutation.mutate(fileId)
  }

  if (isError) {
    return (
      <div className="flex items-center justify-center h-full p-8">
        <QueryError message={error instanceof Error ? error.message : 'Failed to load files'} onRetry={() => refetch()} />
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-red-500">
        <p>Error loading files</p>
        <Button variant="outline" onClick={() => queryClient.invalidateQueries({ queryKey: ['files'] })} className="mt-4">
          <RefreshCw className="h-4 w-4 mr-2" />
          Retry
        </Button>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="border-b bg-card p-4">
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Folder className="h-6 w-6" />
              Files
            </h1>
            <p className="text-muted-foreground mt-1">
              {files.length} item{files.length !== 1 ? 's' : ''} indexed
            </p>
          </div>
          <Button onClick={() => setAddFolderOpen(true)}>
            <Plus className="h-4 w-4 mr-2" />
            Add Folder
          </Button>
        </div>

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            type="text"
            placeholder="Search files..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {(['all', 'indexed', 'processing', 'pending', 'error'] as const).map((status) => (
            <Button
              key={status}
              variant={statusFilter === status ? 'secondary' : 'ghost'}
              size="sm"
              onClick={() => setStatusFilter(status)}
            >
              {status}
            </Button>
          ))}
        </div>
      </div>

      {/* File List */}
      <ScrollArea className="flex-1">
        <div className="p-4">
          {filteredFiles.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <Folder className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p className="text-lg font-medium">No files found</p>
              <p className="text-sm">Add folders to watch in settings</p>
            </div>
          ) : (
            <div className="space-y-1">
              {filteredFiles.map((file: FileItem) => {
                const contentType = file.mime_type || file.content_type
                const Icon = getFileIcon(contentType)
                return (
                  <div
                    key={file.id}
                    data-testid="file-row"
                    className="group flex flex-col gap-3 rounded-lg p-3 transition-colors hover:bg-muted sm:flex-row sm:items-center"
                    onClick={() => setSearchParams({ file: file.id })}
                  >
                    <Icon className={cn("h-5 w-5", getFileColor(contentType))} />
                    <div className="flex-1 min-w-0">
                      <div className="font-medium truncate">{file.filename || file.name}</div>
                      <div className="text-sm text-muted-foreground truncate">{file.path}</div>
                    </div>
                    <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
                      {file.size_bytes !== undefined && (
                        <span className="hidden sm:inline">{formatFileSize(file.size_bytes)}</span>
                      )}
                      {file.last_indexed && (
                        <span className="hidden md:inline">
                          {new Date(file.last_indexed).toLocaleDateString()}
                        </span>
                      )}
                      {file.index_status && (
                        <span className={cn(
                          "text-xs px-2 py-0.5 rounded-full",
                          file.index_status === 'indexed' && 'bg-green-500/10 text-green-600',
                          file.index_status === 'error' && 'bg-red-500/10 text-red-600',
                          file.index_status === 'processing' && 'bg-blue-500/10 text-blue-600',
                          file.index_status === 'pending' && 'bg-yellow-500/10 text-yellow-700'
                        )}>
                          {file.index_status}
                        </span>
                      )}
                      <Button
                        aria-label={`Reindex ${file.filename || file.name || 'file'}`}
                        data-testid="file-reindex-button"
                        variant="ghost"
                        size="icon"
                        className="self-end opacity-100 transition-opacity sm:self-auto sm:opacity-0 sm:group-hover:opacity-100"
                        onClick={(e) => handleReindex(file.id, e)}
                        disabled={reindexingFileId === file.id}
                      >
                        <RefreshCw className={cn("h-4 w-4", reindexingFileId === file.id && "animate-spin")} />
                      </Button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Add Folder Dialog */}
      <Dialog open={addFolderOpen} onOpenChange={setAddFolderOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Watched Folder</DialogTitle>
            <DialogDescription>
              Enter the path to a folder you want to watch for changes.
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <Input
              placeholder="~/Documents or /home/user/Documents"
              value={newFolderPath}
              onChange={(e) => setNewFolderPath(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleAddFolder()}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddFolderOpen(false)}>
              Cancel
            </Button>
            <Button 
              onClick={handleAddFolder}
              disabled={!newFolderPath.trim() || addFolderMutation.isPending}
            >
              {addFolderMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <Plus className="h-4 w-4 mr-2" />
              )}
              Add Folder
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* File Details Dialog */}
      <Dialog open={!!selectedFile} onOpenChange={(open) => !open && setSearchParams({})}>
        <DialogContent className="max-w-2xl">
          {selectedFile && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  {(() => {
                    const Icon = getFileIcon(selectedFile.content_type)
                    return <Icon className={cn("h-5 w-5", getFileColor(selectedFile.mime_type || selectedFile.content_type))} />
                  })()}
                  {selectedFile.filename || selectedFile.name}
                </DialogTitle>
              </DialogHeader>
              <div className="space-y-4 py-4">
                <div className="grid grid-cols-1 gap-4 text-sm sm:grid-cols-2">
                  <div>
                    <span className="text-muted-foreground">Path:</span>
                    <p className="font-mono mt-1">{selectedFile.path}</p>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Type:</span>
                    <p className="mt-1">{selectedFile.mime_type || selectedFile.content_type || 'Unknown'}</p>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Size:</span>
                    <p className="mt-1">{formatFileSize(selectedFile.size_bytes)}</p>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Indexed:</span>
                    <p className="mt-1">{selectedFile.last_indexed ? new Date(selectedFile.last_indexed).toLocaleString() : 'Not indexed'}</p>
                  </div>
                  {(selectedFile.mime_type || selectedFile.content_type) && (
                    <div>
                      <span className="text-muted-foreground">Content Type:</span>
                      <p className="mt-1">{selectedFile.mime_type || selectedFile.content_type}</p>
                    </div>
                  )}
                  {selectedFile.checksum && (
                    <div>
                      <span className="text-muted-foreground">Checksum:</span>
                      <p className="mt-1 font-mono text-xs break-all">{selectedFile.checksum}</p>
                    </div>
                  )}
                  {selectedFile.error_message && (
                    <div className="col-span-2">
                      <span className="text-muted-foreground">Error:</span>
                      <p className="mt-1 text-red-600">{selectedFile.error_message}</p>
                    </div>
                  )}
                </div>
              </div>
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => setSearchParams({})}
                >
                  Close
                </Button>
                <Button 
                  onClick={() => selectedFile && reindexMutation.mutate(selectedFile.id)}
                  disabled={reindexMutation.isPending}
                >
                  {reindexMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  ) : (
                    <RefreshCw className="h-4 w-4 mr-2" />
                  )}
                  Reindex
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
