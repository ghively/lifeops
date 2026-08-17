/**
 * World API wire format.
 *
 * These assert the bytes, not the intent. Every other World test mocks
 * `worldApi`, which cannot catch a request that is well-typed and still wrong
 * on the wire — an array serialised as `types[]=` binds to nothing in FastAPI
 * and the filter is silently ignored rather than failing loudly.
 *
 * The axios adapter is replaced with one that records the request and returns
 * an empty result, so nothing here needs a running LifeOps Core.
 */

import type { AxiosRequestConfig } from 'axios'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { lifeops, worldApi } from '../lifeops'

let seen: AxiosRequestConfig[] = []
let originalAdapter: unknown

beforeEach(() => {
  seen = []
  originalAdapter = lifeops.defaults.adapter
  lifeops.defaults.adapter = ((config: AxiosRequestConfig) => {
    seen.push(config)
    return Promise.resolve({
      data: { nodes: [], edges: [] },
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
    })
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  }) as any
})

afterEach(() => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  lifeops.defaults.adapter = originalAdapter as any
  vi.restoreAllMocks()
})

/** The URL axios would actually put on the wire, params included. */
function requestedUrl(): string {
  return lifeops.getUri(seen[0])
}

describe('graph', () => {
  it('repeats array filters instead of bracketing them', async () => {
    await worldApi.graph({ types: ['household', 'provider'] })

    const url = requestedUrl()
    expect(url).toContain('types=household')
    expect(url).toContain('types=provider')
    expect(url).not.toContain('types%5B%5D')
    expect(url).not.toContain('types[]')
  })

  it('omits empty filters rather than sending blanks', async () => {
    await worldApi.graph({ types: [], query: '' })

    const url = requestedUrl()
    expect(url).not.toContain('types=')
    expect(url).not.toContain('query=')
  })

  it('sends the search text as query', async () => {
    await worldApi.graph({ query: 'ABC Electric' })
    expect(requestedUrl()).toContain('query=ABC')
  })
})

describe('relationships', () => {
  it('links with rel_type in the body', async () => {
    await worldApi.link({
      source_id: 'person_gene',
      target_id: 'household_main',
      rel_type: 'MEMBER_OF',
    })

    expect(seen[0].method).toBe('post')
    expect(JSON.parse(String(seen[0].data))).toEqual({
      source_id: 'person_gene',
      target_id: 'household_main',
      rel_type: 'MEMBER_OF',
    })
  })

  it('unlinks with the triple as query parameters, not a body', async () => {
    await worldApi.unlink({
      source_id: 'person_gene',
      target_id: 'household_main',
      rel_type: 'MEMBER_OF',
    })

    // DELETE bodies are dropped by some proxies and HTTP clients.
    expect(seen[0].method).toBe('delete')
    expect(seen[0].data).toBeUndefined()
    const url = requestedUrl()
    expect(url).toContain('source_id=person_gene')
    expect(url).toContain('target_id=household_main')
    expect(url).toContain('rel_type=MEMBER_OF')
  })
})
