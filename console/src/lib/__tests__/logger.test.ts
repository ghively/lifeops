/**
 * The remote log sink: batched, best-effort, and never a carrier for
 * credentials. The in-memory ring and listener behaviour are unchanged from
 * Phase 0 and not re-tested here.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { _flushRemoteForTest, logger } from '@/lib/logger'
import { systemApi } from '@/services/lifeops'

vi.mock('@/services/lifeops', () => ({
  systemApi: {
    postLogs: vi.fn().mockResolvedValue(undefined),
  },
}))

const mockedPostLogs = vi.mocked(systemApi.postLogs)

beforeEach(() => {
  mockedPostLogs.mockClear()
  mockedPostLogs.mockResolvedValue(undefined)
})

afterEach(() => {
  vi.useRealTimers()
})

describe('logger remote sink', () => {
  it('batches warn/error entries and posts them to /system/logs', async () => {
    logger.warn('TestComponent', 'something odd', { detail: 1 })
    logger.error('TestComponent', 'it broke', { detail: 2 })
    await _flushRemoteForTest()

    expect(mockedPostLogs).toHaveBeenCalledTimes(1)
    const batch = mockedPostLogs.mock.calls[0][0]
    expect(batch).toHaveLength(2)
    expect(batch[0]).toMatchObject({
      level: 'warn',
      message: 'something odd',
    })
    expect(batch[0].context).toMatchObject({ component: 'TestComponent', detail: 1 })
    expect(typeof batch[0].ts).toBe('string')
  })

  it('does not ship debug or info entries', async () => {
    logger.debug('TestComponent', 'noise')
    logger.info('TestComponent', 'still noise')
    await _flushRemoteForTest()
    expect(mockedPostLogs).not.toHaveBeenCalled()
  })

  it('redacts fields whose keys look like credentials', async () => {
    logger.error('TestComponent', 'failure', {
      api_key: 'sk-live-secret',
      password: 'hunter2',
      note: 'safe',
    })
    await _flushRemoteForTest()

    const context = mockedPostLogs.mock.calls[0][0][0].context ?? {}
    expect(context.api_key).toBe('[redacted]')
    expect(context.password).toBe('[redacted]')
    expect(context.note).toBe('safe')
  })

  it('swallows backend failures instead of throwing or looping', async () => {
    mockedPostLogs.mockRejectedValue(new Error('server down'))
    logger.error('TestComponent', 'will be lost')
    await expect(_flushRemoteForTest()).resolves.toBeUndefined()
  })

  it('flushes automatically once the batch threshold is reached', async () => {
    for (let i = 0; i < 10; i += 1) {
      logger.error('TestComponent', `error ${i}`)
    }
    // Threshold triggers an immediate flush — no timer needed.
    await vi.waitFor(() => expect(mockedPostLogs).toHaveBeenCalled())
    expect(mockedPostLogs.mock.calls[0][0].length).toBe(10)
    await _flushRemoteForTest() // clear the scheduled timer left by entries 1–9
  })

  it('flushes on a timer below the batch threshold', async () => {
    vi.useFakeTimers()
    logger.warn('TestComponent', 'single warning')
    expect(mockedPostLogs).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(5_000)
    expect(mockedPostLogs).toHaveBeenCalledTimes(1)
  })
})
