/**
 * Tests for the API service.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import axios from 'axios'

// Mock axios before importing api
vi.mock('axios', () => {
  const mockInterceptors = {
    request: { use: vi.fn() },
    response: { use: vi.fn() },
  }
  const mockInstance = {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
    interceptors: mockInterceptors,
    defaults: { headers: { common: {} } },
  }
  return {
    default: {
      create: vi.fn(() => mockInstance),
    },
    create: vi.fn(() => mockInstance),
  }
})

// Import after mock
import { APIError, agentRuntimeApi, api } from '../api'

const mockApi = api as any

describe('API Service', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.unstubAllGlobals()
    // Mock localStorage
    const store: Record<string, string> = {}
    Object.defineProperty(window, 'localStorage', {
      value: {
        getItem: vi.fn((key: string) => store[key] || null),
        setItem: vi.fn((key: string, value: string) => { store[key] = value }),
        removeItem: vi.fn((key: string) => { delete store[key] }),
      },
      configurable: true,
    })
  })

  describe('objects', () => {
    it('should fetch objects', async () => {
      mockApi.get.mockResolvedValue({ data: { objects: [], total: 0 } })
      const result = await api.get('/api/v1/objects')
      expect(mockApi.get).toHaveBeenCalledWith('/api/v1/objects')
      expect(result.data).toEqual({ objects: [], total: 0 })
    })

    it('should create an object', async () => {
      const newObject = { title: 'Test', content: 'Test content', type: 'note' }
      mockApi.post.mockResolvedValue({ data: { id: '123', ...newObject } })
      const result = await api.post('/api/v1/objects', newObject)
      expect(mockApi.post).toHaveBeenCalledWith('/api/v1/objects', newObject)
      expect(result.data.id).toBe('123')
    })

    it('should update an object', async () => {
      mockApi.put.mockResolvedValue({ data: { id: '123', title: 'Updated' } })
      const result = await api.put('/api/v1/objects/123', { title: 'Updated' })
      expect(mockApi.put).toHaveBeenCalledWith('/api/v1/objects/123', { title: 'Updated' })
    })

    it('should delete an object', async () => {
      mockApi.delete.mockResolvedValue({ data: { message: 'Deleted' } })
      const result = await api.delete('/api/v1/objects/123')
      expect(mockApi.delete).toHaveBeenCalledWith('/api/v1/objects/123')
    })
  })

  describe('blocks', () => {
    it('should fetch blocks for an object', async () => {
      mockApi.get.mockResolvedValue({ data: { blocks: [] } })
      const result = await api.get('/api/v1/blocks/object/obj-1')
      expect(result.data).toEqual({ blocks: [] })
    })

    it('should create a block', async () => {
      const block = { object_id: 'obj-1', content: 'Block content', type: 'paragraph' }
      mockApi.post.mockResolvedValue({ data: { id: 'blk-1', ...block } })
      const result = await api.post('/api/v1/blocks', block)
      expect(result.data.id).toBe('blk-1')
    })
  })

  describe('search', () => {
    it('should search with query', async () => {
      mockApi.get.mockResolvedValue({ data: { results: [] } })
      const result = await api.get('/api/v1/search', { params: { q: 'test' } })
      expect(mockApi.get).toHaveBeenCalledWith('/api/v1/search', { params: { q: 'test' } })
      expect(result.data).toEqual({ results: [] })
    })
  })

  describe('tasks', () => {
    it('should list tasks', async () => {
      mockApi.get.mockResolvedValue({ data: { tasks: [], by_status: {}, by_priority: {} } })
      const result = await api.get('/api/v1/tasks')
      expect(result.data.tasks).toEqual([])
    })
  })

  describe('error handling', () => {
    it('should handle network errors', async () => {
      mockApi.get.mockRejectedValue(new Error('Network error'))
      await expect(api.get('/api/v1/objects')).rejects.toThrow('Network error')
    })

    it('should handle 404 errors', async () => {
      const error = { response: { status: 404, data: { detail: 'Not found' } } }
      mockApi.get.mockRejectedValue(error)
      await expect(api.get('/api/v1/objects/nonexistent')).rejects.toEqual(error)
    })

    it('should preserve rate limit payloads for streaming chat', async () => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
        ok: false,
        status: 429,
        json: vi.fn().mockResolvedValue({
          detail: 'Rate limit exceeded',
          retry_after_seconds: 15,
        }),
      }))

      await expect(agentRuntimeApi.chatWithAgent({ agent_id: 'agent-1', message: 'hello' })).rejects.toMatchObject({
        name: 'APIError',
        statusCode: 429,
        response: {
          retry_after_seconds: 15,
        },
      } satisfies Partial<APIError>)
    })
  })
})
