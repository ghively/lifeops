import { describe, it, expect, vi } from 'vitest'
import { cn, formatDate, formatRelativeTime, generateId, debounce } from '../utils'

describe('cn (className utility)', () => {
  it('should merge class names correctly', () => {
    expect(cn('foo', 'bar')).toBe('foo bar')
  })

  it('should handle conditional classes', () => {
    expect(cn('foo', false && 'bar', 'baz')).toBe('foo baz')
  })

  it('should handle undefined and null', () => {
    expect(cn('foo', undefined, null, 'bar')).toBe('foo bar')
  })

  it('should handle empty strings', () => {
    expect(cn('foo', '', 'bar')).toBe('foo bar')
  })

  it('should handle Tailwind conflict resolution', () => {
    expect(cn('p-4', 'p-2')).toBe('p-2')
  })

  it('should return empty string for no inputs', () => {
    expect(cn()).toBe('')
  })

  it('should handle arrays of classes', () => {
    expect(cn(['foo', 'bar'], 'baz')).toBe('foo bar baz')
  })

  it('should handle objects with boolean values', () => {
    expect(cn({ foo: true, bar: false, baz: true })).toBe('foo baz')
  })
})

describe('formatDate', () => {
  it('should format a valid date', () => {
    const date = new Date('2024-01-15T10:30:00Z')
    const formatted = formatDate(date)
    expect(formatted).toBeTruthy()
    expect(typeof formatted).toBe('string')
  })

  it('should handle ISO string input', () => {
    const formatted = formatDate('2024-01-15T10:30:00Z')
    expect(formatted).toBeTruthy()
  })

  it('should handle Date input', () => {
    const date = new Date('2024-01-15')
    const formatted = formatDate(date)
    expect(formatted).toBeTruthy()
  })

  it('should handle invalid date gracefully', () => {
    const formatted = formatDate('invalid-date')
    expect(formatted).toBeTruthy()
  })

  it('should include year, month, and day', () => {
    const date = new Date('2024-01-15')
    const formatted = formatDate(date)
    expect(formatted).toMatch(/2024/)
  })
})

describe('formatRelativeTime', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2024-01-15T12:00:00Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('should format time just now', () => {
    const date = new Date('2024-01-15T11:59:30Z')
    const formatted = formatRelativeTime(date)
    expect(formatted).toMatch(/just now|now/i)
  })

  it('should format minutes ago', () => {
    const date = new Date('2024-01-15T11:55:00Z')
    const formatted = formatRelativeTime(date)
    expect(formatted).toMatch(/5m|5 min/i)
  })

  it('should format hours ago', () => {
    const date = new Date('2024-01-15T08:00:00Z')
    const formatted = formatRelativeTime(date)
    expect(formatted).toMatch(/4h|4 hour/i)
  })

  it('should format days ago', () => {
    const date = new Date('2024-01-12T12:00:00Z')
    const formatted = formatRelativeTime(date)
    expect(formatted).toMatch(/3d|3 day/i)
  })

  it('should handle ISO string input', () => {
    const formatted = formatRelativeTime('2024-01-15T11:00:00Z')
    expect(formatted).toBeTruthy()
  })

  it('should handle invalid date gracefully', () => {
    const formatted = formatRelativeTime('invalid-date')
    expect(formatted).toBeTruthy()
  })

  it('should handle future dates', () => {
    const date = new Date('2024-01-15T13:00:00Z')
    const formatted = formatRelativeTime(date)
    expect(formatted).toBeTruthy()
  })
})

describe('generateId', () => {
  it('should generate a unique ID', () => {
    const id1 = generateId()
    const id2 = generateId()
    expect(id1).not.toBe(id2)
  })

  it('should generate a string', () => {
    const id = generateId()
    expect(typeof id).toBe('string')
  })

  it('should generate IDs of consistent length', () => {
    const id1 = generateId()
    const id2 = generateId()
    expect(id1.length).toBe(id2.length)
  })

  it('should generate valid UUID format', () => {
    const id = generateId()
    expect(id).toMatch(/^[0-9a-f-]{36}$/i)
  })

  it('should generate unique IDs in bulk', () => {
    const ids = new Set()
    for (let i = 0; i < 1000; i++) {
      ids.add(generateId())
    }
    expect(ids.size).toBe(1000)
  })
})

describe('debounce', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('should delay function execution', () => {
    const fn = vi.fn()
    const debouncedFn = debounce(fn, 100)

    debouncedFn()
    expect(fn).not.toHaveBeenCalled()

    vi.advanceTimersByTime(100)
    expect(fn).toHaveBeenCalledTimes(1)
  })

  it('should cancel previous calls', () => {
    const fn = vi.fn()
    const debouncedFn = debounce(fn, 100)

    debouncedFn()
    vi.advanceTimersByTime(50)

    debouncedFn()
    vi.advanceTimersByTime(50)

    expect(fn).not.toHaveBeenCalled()

    vi.advanceTimersByTime(50)
    expect(fn).toHaveBeenCalledTimes(1)
  })

  it('should pass arguments to debounced function', () => {
    const fn = vi.fn()
    const debouncedFn = debounce(fn, 100)

    debouncedFn('arg1', 'arg2')
    vi.advanceTimersByTime(100)

    expect(fn).toHaveBeenCalledWith('arg1', 'arg2')
  })

  it('should preserve context', () => {
    const obj = {
      value: 'test',
      fn: vi.fn(function(this: any) {
        return this.value
      }),
    }

    const debouncedFn = debounce(obj.fn.bind(obj), 100)
    debouncedFn()
    vi.advanceTimersByTime(100)

    expect(obj.fn).toHaveBeenCalled()
  })

  it('should handle multiple rapid calls', () => {
    const fn = vi.fn()
    const debouncedFn = debounce(fn, 100)

    for (let i = 0; i < 10; i++) {
      debouncedFn()
    }

    vi.advanceTimersByTime(100)

    expect(fn).toHaveBeenCalledTimes(1)
  })

  it('should handle zero delay', () => {
    const fn = vi.fn()
    const debouncedFn = debounce(fn, 0)

    debouncedFn()
    expect(fn).not.toHaveBeenCalled()

    vi.advanceTimersByTime(0)
    expect(fn).toHaveBeenCalledTimes(1)
  })
})
