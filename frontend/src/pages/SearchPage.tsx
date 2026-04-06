import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Search, FileText, Folder, Image, Code, Loader2 } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { searchApi, type SearchResult } from '@/services/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import { QueryError } from '@/components/QueryError'

const typeIcons: Record<string, typeof FileText> = {
  object: FileText,
  block: FileText,
  file: Folder,
  image: Image,
  code: Code,
}

const typeColors: Record<string, string> = {
  object: 'text-blue-500',
  block: 'text-gray-500',
  file: 'text-yellow-500',
  image: 'text-purple-500',
  code: 'text-green-500',
}

export function SearchPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const initialQuery = searchParams.get('q') || ''
  const initialType = searchParams.get('type') === 'exact' ? 'exact' : 'semantic'
  const [query, setQuery] = useState(initialQuery)
  const [activeQuery, setActiveQuery] = useState(initialQuery)
  const [searchType, setSearchType] = useState<'semantic' | 'exact'>(initialType)

  const { data: resultsData, isLoading, error, refetch } = useQuery({
    queryKey: ['search', activeQuery, searchType],
    queryFn: () => {
      if (!activeQuery) {
        return Promise.resolve({ results: [] as SearchResult[] })
      }
      return searchApi.search(activeQuery, searchType)
    },
    enabled: !!activeQuery,
  })
  const results = resultsData?.results ?? []

  useEffect(() => {
    if (initialQuery) {
      setQuery(initialQuery)
      setActiveQuery(initialQuery)
    }
    setSearchType(initialType)
  }, [initialQuery, initialType])

  const handleSearch = () => {
    if (query.trim()) {
      setActiveQuery(query)
      setSearchParams({ q: query, type: searchType })
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch()
    }
  }

  const handleResultClick = (result: SearchResult) => {
    switch (result.collection) {
      case 'objects':
      case 'blocks':
        navigate(`/object/${result.id}`)
        break
      case 'files':
        navigate(`/files?file=${result.id}`)
        break
      case 'code':
        if (typeof (result as SearchResult & { object_id?: string }).object_id === 'string') {
          navigate(`/object/${(result as SearchResult & { object_id?: string }).object_id}`)
          break
        }
        navigate(`/files?file=${result.id}`)
        break
      case 'images':
        if (typeof (result as SearchResult & { source_file?: string }).source_file === 'string') {
          navigate(`/files?file=${(result as SearchResult & { source_file?: string }).source_file}`)
          break
        }
        navigate(`/files?file=${result.id}`)
        break
      default:
        navigate(`/search?q=${encodeURIComponent(result.title || result.filename || result.id)}&type=${searchType}`)
        break
    }
  }

  return (
    <div className="h-full flex flex-col">
      {/* Search Header */}
      <div className="border-b bg-card p-4">
        <div className="max-w-3xl mx-auto">
          <h1 className="text-2xl font-bold mb-4">Search</h1>
          
          <div className="flex flex-col gap-2 sm:flex-row">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Search across all your knowledge..."
                className="pl-10"
              />
            </div>
            <Button 
              onClick={handleSearch}
              disabled={isLoading || !query.trim()}
            >
              {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Search'}
            </Button>
          </div>

          {/* Search Type Toggle */}
          <div className="mt-3 flex flex-wrap gap-2">
            <Button
              variant={searchType === 'semantic' ? 'secondary' : 'ghost'}
              size="sm"
              onClick={() => setSearchType('semantic')}
            >
              Semantic Search
            </Button>
            <Button
              variant={searchType === 'exact' ? 'secondary' : 'ghost'}
              size="sm"
              onClick={() => setSearchType('exact')}
            >
              Exact Match
            </Button>
          </div>
        </div>
      </div>

      {/* Results */}
      <ScrollArea className="flex-1">
        <div className="max-w-3xl mx-auto p-4">
          {!activeQuery ? (
            <div className="text-center py-12 text-muted-foreground">
              <Search className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p className="text-lg font-medium">Start searching</p>
              <p className="text-sm">Type a query above to search across your knowledge base</p>
            </div>
          ) : isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : error ? (
            <QueryError message={error instanceof Error ? error.message : 'Search failed'} onRetry={() => refetch()} />
          ) : results.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <p className="text-lg font-medium">No results found</p>
              <p className="text-sm">Try a different search term or check your spelling</p>
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground mb-4">
                Found {results.length} result{results.length !== 1 ? 's' : ''}
              </p>
              
              {results.map((result: SearchResult) => {
                const resultType = result.collection === 'objects' ? 'object' : result.collection
                const Icon = typeIcons[resultType] || FileText
                const resultTitle = result.title || result.filename || result.id
                const resultContent = result.content || result.context || ''
                return (
                  <div
                    key={result.id}
                    data-testid="search-result"
                    onClick={() => handleResultClick(result)}
                    className="p-4 border rounded-lg hover:bg-muted cursor-pointer transition-colors"
                  >
                    <div className="flex items-start gap-3">
                      <Icon className={cn("h-5 w-5 mt-0.5 flex-shrink-0", typeColors[resultType] || 'text-gray-500')} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <h3 className="font-medium truncate">{resultTitle}</h3>
                          <span className="text-xs text-muted-foreground">
                            {Math.round(result.score * 100)}% match
                          </span>
                        </div>
                        <p className="text-sm text-muted-foreground line-clamp-2 mt-1">
                          {resultContent}
                        </p>
                        <div className="flex items-center gap-2 mt-2">
                          <span className="text-xs px-2 py-0.5 bg-muted rounded-full capitalize">
                            {resultType}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  )
}
