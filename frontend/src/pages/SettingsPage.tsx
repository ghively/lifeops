import { useState, useEffect } from 'react'
import { Settings, Folder, Database, Bot, Save, Plus, Trash2, Loader2, RefreshCw, Download, GitBranch } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { settingsApi } from '@/services/api'

interface WatchedFolder {
  id: string
  path: string
  recursive: boolean
  file_count: number
}

interface Settings {
  openclaw_url: string
  openclaw_token?: string
  openclaw_enabled?: boolean
  backup_snapshots: boolean
  backup_markdown: boolean
  backup_git: boolean
  git_repo_url?: string
  snapshot_interval_hours?: number
  markdown_export_interval_hours?: number
  git_sync_interval_minutes?: number
  embedding_model?: string
  auto_index: boolean
}

export function SettingsPage() {
  const queryClient = useQueryClient()
  const [settings, setSettings] = useState<Settings>({
    openclaw_url: 'http://localhost:18789',
    openclaw_token: '',
    openclaw_enabled: true,
    backup_snapshots: true,
    backup_markdown: true,
    backup_git: false,
    git_repo_url: '',
    snapshot_interval_hours: 24,
    markdown_export_interval_hours: 168,
    git_sync_interval_minutes: 30,
    embedding_model: 'all-MiniLM-L6-v2',
    auto_index: true,
  })
  const [addFolderOpen, setAddFolderOpen] = useState(false)
  const [newFolderPath, setNewFolderPath] = useState('')
  const [newFolderRecursive, setNewFolderRecursive] = useState(true)

  // Fetch current settings
  const { data: currentSettings, isLoading: settingsLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: settingsApi.get,
  })

  // Fetch watched folders
  const { data: watchedFoldersData, isLoading: foldersLoading } = useQuery({
    queryKey: ['watched-folders'],
    queryFn: settingsApi.getWatchedFolders,
  })
  const watchedFolders = watchedFoldersData?.folders ?? []

  // Update local settings when data loads
  useEffect(() => {
    if (currentSettings) {
      setSettings(currentSettings)
    }
  }, [currentSettings])

  // Save settings mutation
  const saveSettingsMutation = useMutation({
    mutationFn: (newSettings: Settings) => settingsApi.update(newSettings),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] })
    },
  })

  // Add folder mutation
  const addFolderMutation = useMutation({
    mutationFn: ({ path, recursive }: { path: string; recursive: boolean }) =>
      settingsApi.addWatchedFolder(path, recursive),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['watched-folders'] })
      setAddFolderOpen(false)
      setNewFolderPath('')
    },
  })

  // Remove folder mutation
  const removeFolderMutation = useMutation({
    mutationFn: (folderId: string) => settingsApi.removeWatchedFolder(folderId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['watched-folders'] })
    },
  })

  // Trigger backup mutation
  const backupMutation = useMutation({
    mutationFn: (type: 'snapshot' | 'markdown' | 'git') => settingsApi.triggerBackup(type),
  })

  const handleSave = () => {
    saveSettingsMutation.mutate(settings)
  }

  const handleAddFolder = () => {
    if (newFolderPath.trim()) {
      addFolderMutation.mutate({ path: newFolderPath.trim(), recursive: newFolderRecursive })
    }
  }

  const handleRemoveFolder = (folderId: string) => {
    removeFolderMutation.mutate(folderId)
  }

  if (settingsLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col">
      <ScrollArea className="flex-1">
        <div className="max-w-4xl mx-auto py-8 px-6">
          {/* Header */}
          <div className="mb-6">
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Settings className="h-6 w-6" />
              Settings
            </h1>
            <p className="text-muted-foreground mt-1">
              Configure your Knowledge OS
            </p>
          </div>

          <div className="space-y-8">
            {/* OpenClaw Settings */}
            <section className="bg-card border rounded-lg p-6">
              <div className="flex items-center gap-2 mb-4">
                <Bot className="h-5 w-5" />
                <h2 className="text-lg font-semibold">OpenClaw Integration</h2>
              </div>
              
              <div className="space-y-4">
                <div className="flex items-start space-x-3">
                  <Checkbox
                    id="openclaw-enabled"
                    checked={settings.openclaw_enabled}
                    onCheckedChange={(checked) => setSettings({ ...settings, openclaw_enabled: checked as boolean })}
                  />
                  <div>
                    <Label htmlFor="openclaw-enabled" className="font-medium">
                      Enable OpenClaw
                    </Label>
                    <p className="text-sm text-muted-foreground">
                      Turn agent gateway integration on or off without changing your config.
                    </p>
                  </div>
                </div>
                <div>
                  <Label htmlFor="openclaw-url">Gateway URL</Label>
                  <Input
                    id="openclaw-url"
                    type="text"
                    value={settings.openclaw_url}
                    onChange={(e) => setSettings({ ...settings, openclaw_url: e.target.value })}
                    placeholder="http://localhost:18789"
                  />
                  <p className="text-sm text-muted-foreground mt-1">
                    The URL of your OpenClaw gateway
                  </p>
                </div>
                
                <div>
                  <Label htmlFor="openclaw-token">Gateway Token (optional)</Label>
                  <Input
                    id="openclaw-token"
                    type="password"
                    value={settings.openclaw_token}
                    onChange={(e) => setSettings({ ...settings, openclaw_token: e.target.value })}
                    placeholder="Your gateway token"
                  />
                </div>
              </div>
            </section>

            {/* Watched Folders */}
            <section className="bg-card border rounded-lg p-6">
              <div className="flex items-center gap-2 mb-4">
                <Folder className="h-5 w-5" />
                <h2 className="text-lg font-semibold">Watched Folders</h2>
              </div>
              
              <div className="space-y-2">
                {foldersLoading ? (
                  <div className="text-center py-4">
                    <Loader2 className="h-6 w-6 animate-spin mx-auto text-muted-foreground" />
                  </div>
                ) : watchedFolders.length === 0 ? (
                  <div className="text-center py-4 text-muted-foreground">
                    No folders being watched
                  </div>
                ) : (
                  watchedFolders.map((folder: WatchedFolder) => (
                    <div key={folder.id} className="flex items-center justify-between p-3 bg-muted rounded-md">
                      <div>
                        <div className="font-medium">{folder.path}</div>
                        <div className="text-sm text-muted-foreground">
                          {folder.recursive ? 'Recursive' : 'Non-recursive'} • {folder.file_count} files
                        </div>
                      </div>
                      <Button
                        aria-label={`Remove watched folder ${folder.path}`}
                        data-testid="remove-folder-button"
                        variant="ghost"
                        size="sm"
                        onClick={() => handleRemoveFolder(folder.id)}
                        disabled={removeFolderMutation.isPending}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  ))
                )}
              </div>
              
              <Button variant="outline" className="mt-4" onClick={() => setAddFolderOpen(true)}>
                <Plus className="h-4 w-4 mr-2" />
                Add Folder
              </Button>
            </section>

            {/* Backup Settings */}
            <section className="bg-card border rounded-lg p-6">
              <div className="flex items-center gap-2 mb-4">
                <Database className="h-5 w-5" />
                <h2 className="text-lg font-semibold">Backup & Export</h2>
              </div>
              
              <div className="space-y-4">
                <div className="flex items-start space-x-3">
                  <Checkbox
                    id="backup-snapshots"
                    checked={settings.backup_snapshots}
                    onCheckedChange={(checked) =>
                      setSettings({ ...settings, backup_snapshots: checked as boolean })
                    }
                  />
                  <div className="flex-1">
                    <Label htmlFor="backup-snapshots" className="font-medium">
                      Qdrant Snapshots
                    </Label>
                    <p className="text-sm text-muted-foreground">
                      Daily automatic backups of your vector database
                    </p>
                    <Input
                      className="mt-2 max-w-xs"
                      type="number"
                      value={settings.snapshot_interval_hours}
                      onChange={(e) => setSettings({ ...settings, snapshot_interval_hours: Number(e.target.value) })}
                      placeholder="24"
                    />
                  </div>
                  <Button
                    aria-label="Trigger Qdrant snapshots backup"
                    data-testid="snapshot-backup-button"
                    variant="ghost"
                    size="sm"
                    onClick={() => backupMutation.mutate('snapshot')}
                    disabled={backupMutation.isPending}
                  >
                    <Download className="h-4 w-4" />
                  </Button>
                </div>
                
                <div className="flex items-start space-x-3">
                  <Checkbox
                    id="backup-markdown"
                    checked={settings.backup_markdown}
                    onCheckedChange={(checked) =>
                      setSettings({ ...settings, backup_markdown: checked as boolean })
                    }
                  />
                  <div className="flex-1">
                    <Label htmlFor="backup-markdown" className="font-medium">
                      Markdown Export
                    </Label>
                    <p className="text-sm text-muted-foreground">
                      Weekly export to markdown files
                    </p>
                    <Input
                      className="mt-2 max-w-xs"
                      type="number"
                      value={settings.markdown_export_interval_hours}
                      onChange={(e) => setSettings({ ...settings, markdown_export_interval_hours: Number(e.target.value) })}
                      placeholder="168"
                    />
                  </div>
                  <Button
                    aria-label="Trigger markdown export backup"
                    data-testid="markdown-backup-button"
                    variant="ghost"
                    size="sm"
                    onClick={() => backupMutation.mutate('markdown')}
                    disabled={backupMutation.isPending}
                  >
                    <Download className="h-4 w-4" />
                  </Button>
                </div>
                
                <div className="flex items-start space-x-3">
                  <Checkbox
                    id="backup-git"
                    checked={settings.backup_git}
                    onCheckedChange={(checked) =>
                      setSettings({ ...settings, backup_git: checked as boolean })
                    }
                  />
                  <div className="flex-1">
                    <Label htmlFor="backup-git" className="font-medium">
                      Git Sync
                    </Label>
                    <p className="text-sm text-muted-foreground">
                      Sync to Git repository
                    </p>
                    <Input
                      className="mt-2 max-w-xs"
                      type="number"
                      value={settings.git_sync_interval_minutes}
                      onChange={(e) => setSettings({ ...settings, git_sync_interval_minutes: Number(e.target.value) })}
                      placeholder="30"
                    />
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => backupMutation.mutate('git')}
                    disabled={backupMutation.isPending}
                  >
                    <GitBranch className="h-4 w-4" />
                  </Button>
                </div>

                {settings.backup_git && (
                  <div className="pl-7">
                    <Label htmlFor="git-repo-url">Git Repository URL</Label>
                    <Input
                      id="git-repo-url"
                      type="text"
                      value={settings.git_repo_url}
                      onChange={(e) => setSettings({ ...settings, git_repo_url: e.target.value })}
                      placeholder="https://github.com/user/repo.git"
                    />
                  </div>
                )}
              </div>
            </section>

            {/* Indexing Settings */}
            <section className="bg-card border rounded-lg p-6">
              <div className="flex items-center gap-2 mb-4">
                <RefreshCw className="h-5 w-5" />
                <h2 className="text-lg font-semibold">Indexing</h2>
              </div>
              
              <div className="flex items-start space-x-3">
                <Checkbox
                  id="auto-index"
                  checked={settings.auto_index}
                  onCheckedChange={(checked) =>
                    setSettings({ ...settings, auto_index: checked as boolean })
                  }
                />
                <div>
                  <Label htmlFor="auto-index" className="font-medium">
                    Auto-index new files
                  </Label>
                  <p className="text-sm text-muted-foreground">
                    Automatically index new files as they are added to watched folders
                  </p>
                </div>
              </div>
              <div className="mt-4">
                <Label htmlFor="embedding-model">Embedding Model</Label>
                <Input
                  id="embedding-model"
                  value={settings.embedding_model}
                  onChange={(e) => setSettings({ ...settings, embedding_model: e.target.value })}
                />
              </div>
            </section>
          </div>

          {/* Save Button */}
          <div className="mt-8 flex justify-end">
            <Button 
              onClick={handleSave}
              disabled={saveSettingsMutation.isPending}
            >
              {saveSettingsMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <Save className="h-4 w-4 mr-2" />
              )}
              Save Changes
            </Button>
          </div>
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
          <div className="space-y-4 py-4">
            <div>
              <Label htmlFor="folder-path">Folder Path</Label>
              <Input
                id="folder-path"
                placeholder="~/Documents or /home/user/Documents"
                value={newFolderPath}
                onChange={(e) => setNewFolderPath(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleAddFolder()}
              />
            </div>
            <div className="flex items-center space-x-2">
              <Checkbox
                id="recursive"
                checked={newFolderRecursive}
                onCheckedChange={(checked) => setNewFolderRecursive(checked as boolean)}
              />
              <Label htmlFor="recursive">Watch recursively (include subfolders)</Label>
            </div>
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
    </div>
  )
}
