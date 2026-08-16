import { render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApprovalDialog } from '../ApprovalDialog'

describe('ApprovalDialog', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('auto-rejects once when the timer expires', async () => {
    const onDecision = vi.fn()

    render(
      <ApprovalDialog
        open
        onDecision={onDecision}
        approval={{
          request_id: 'req-1',
          tool_name: 'write_file',
          timeout_seconds: 1,
          arguments: {},
        }}
      />
    )

    await vi.advanceTimersByTimeAsync(1000)

    expect(onDecision).toHaveBeenCalledTimes(1)
    expect(onDecision).toHaveBeenCalledWith(false)
  })
})
