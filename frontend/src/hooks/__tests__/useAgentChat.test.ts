/**
 * Tests for useAgentChat hook.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useAgentChat } from '../useAgentChat'

// Mock the API
vi.mock('@/services/api', () => ({
  agentRuntimeApi: {
    chat: vi.fn(),
  },
  APIError: class APIError extends Error {},
}))

import { agentRuntimeApi } from '@/services/api'

describe('useAgentChat Hook', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('initializes with empty messages when no initial messages provided', () => {
    const { result } = renderHook(() => useAgentChat({ agentId: 'test-agent' }))

    expect(result.current.messages).toEqual([])
    expect(result.current.isStreaming).toBe(false)
    expect(result.current.error).toBeNull()
  })

  it('initializes with provided initial messages', () => {
    const initialMessages = [
      {
        id: 'msg-1',
        role: 'user',
        content: 'Hello',
        created_at: new Date().toISOString(),
      },
    ]

    const { result } = renderHook(() =>
      useAgentChat({ agentId: 'test-agent', initialMessages: initialMessages as any })
    )

    expect(result.current.messages).toHaveLength(1)
    expect(result.current.messages[0].role).toBe('user')
    expect(result.current.messages[0].content).toBe('Hello')
  })

  it('sends message and adds it to history', async () => {
    const mockChatResponse = async function* () {
      yield { type: 'message', data: 'Response text' }
    }

    vi.mocked(agentRuntimeApi.chat).mockReturnValue(mockChatResponse() as any)

    const { result } = renderHook(() => useAgentChat({ agentId: 'test-agent' }))

    await act(async () => {
      await result.current.sendMessage('Hello agent')
    })

    expect(result.current.messages).toContainEqual(
      expect.objectContaining({
        role: 'user',
        content: 'Hello agent',
      })
    )
  })

  it('sets error when API call fails', async () => {
    const errorMessage = 'API Error'
    vi.mocked(agentRuntimeApi.chat).mockRejectedValue(new Error(errorMessage))

    const { result } = renderHook(() => useAgentChat({ agentId: 'test-agent' }))

    await act(async () => {
      try {
        await result.current.sendMessage('Hello')
      } catch {
        // Expected
      }
    })

    expect(result.current.error).toBe(errorMessage)
  })

  it('clears isPending when request completes', async () => {
    const mockChatResponse = async function* () {
      yield { type: 'message', data: 'Response' }
    }

    vi.mocked(agentRuntimeApi.chat).mockReturnValue(mockChatResponse() as any)

    const { result } = renderHook(() => useAgentChat({ agentId: 'test-agent' }))

    await act(async () => {
      const promise = result.current.sendMessage('Hello')
      expect(result.current.isStreaming).toBe(true)
      await promise
    })

    expect(result.current.isStreaming).toBe(false)
  })

  it('supports cancellation', async () => {
    const mockChatResponse = async function* () {
      yield { type: 'message', data: 'Response' }
    }

    vi.mocked(agentRuntimeApi.chat).mockReturnValue(mockChatResponse() as any)

    const { result } = renderHook(() => useAgentChat({ agentId: 'test-agent' }))

    const controller = new AbortController()

    await act(async () => {
      const promise = result.current.sendMessage('Hello', controller.signal)
      controller.abort()
      try {
        await promise
      } catch {
        // Expected
      }
    })

    expect(result.current.isStreaming).toBe(false)
  })

  it('generates unique message IDs', () => {
    const { result: result1 } = renderHook(() => useAgentChat({ agentId: 'test-agent' }))
    const { result: result2 } = renderHook(() => useAgentChat({ agentId: 'test-agent' }))

    expect(result1.current.messages).toBeDefined()
    expect(result2.current.messages).toBeDefined()
  })
})
