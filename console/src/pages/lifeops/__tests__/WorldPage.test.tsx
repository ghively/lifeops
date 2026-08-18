/**
 * World screen behaviour (BUILD_SPEC sections 15, 16, 92).
 *
 * The properties under test are the ones the graph library cannot give us and
 * that a type-check alone would not catch: the entity-type filter reaches the
 * API as repeated values, clicking a node expands its neighborhood, the
 * inspector reads the aggregate the server actually sends, linking submits
 * `rel_type`, and unlinking identifies the edge by its stored direction.
 *
 * React Flow is stubbed: it needs real layout, and what matters here is which
 * nodes and edges the page hands it, not how they are drawn.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { WorldPage } from '../WorldPage'
import {
  preferencesApi,
  worldApi,
  type MemoryRecord,
  type Task,
  type WorldEntityDetail,
  type WorldGraph,
} from '@/services/lifeops'

vi.mock('@/services/lifeops', async () => {
  const actual = await vi.importActual<typeof import('@/services/lifeops')>(
    '@/services/lifeops',
  )
  return {
    ...actual,
    worldApi: {
      graph: vi.fn(),
      neighborhood: vi.fn(),
      entity: vi.fn(),
      history: vi.fn(),
      createEntity: vi.fn(),
      link: vi.fn(),
      unlink: vi.fn(),
    },
    preferencesApi: {
      history: vi.fn(),
    },
  }
})

/** A stand-in canvas that renders one button per node and lists the edges. */
vi.mock('@/components/world/WorldGraph', () => ({
  WorldGraphView: ({
    graph,
    onNodeClick,
  }: {
    graph: WorldGraph
    onNodeClick: (id: string) => void
  }) => (
    <div data-testid="graph">
      {graph.nodes.map((node) => (
        <button key={node.id} type="button" onClick={() => onNodeClick(node.id)}>
          node:{node.label}
        </button>
      ))}
      {graph.edges.map((edge) => (
        <span key={`${edge.source}|${edge.type}|${edge.target}`}>
          edge:{edge.source}-{edge.type}-{edge.target}
        </span>
      ))}
    </div>
  ),
}))

const PERSON = 'person_gene'
const HOUSEHOLD = 'household_main'
const PROVIDER = 'provider_abc_electric'

function graph(): WorldGraph {
  return {
    nodes: [
      { id: PERSON, entity_type: 'person', label: 'Gene', status: 'active' },
      { id: HOUSEHOLD, entity_type: 'household', label: 'Main House', status: 'active' },
    ],
    edges: [{ source: PERSON, target: HOUSEHOLD, type: 'MEMBER_OF' }],
  }
}

function detail(overrides: Partial<WorldEntityDetail> = {}): WorldEntityDetail {
  return {
    entity: {
      id: HOUSEHOLD,
      entity_type: 'household',
      display_name: 'Main House',
      facts: { address: '12 Elm Street' },
      created_at: '2026-08-16T10:00:00Z',
      updated_at: '2026-08-16T10:00:00Z',
      created_by_client: 'lifeops-console',
    },
    relationships: [{ source: PERSON, target: HOUSEHOLD, type: 'MEMBER_OF' }],
    neighbors: [{ id: PERSON, entity_type: 'person', label: 'Gene', status: 'active' }],
    related_tasks: [],
    related_memories: [],
    ...overrides,
  }
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <WorldPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.mocked(worldApi.graph).mockResolvedValue(graph())
  vi.mocked(worldApi.neighborhood).mockResolvedValue({
    nodes: [
      { id: HOUSEHOLD, entity_type: 'household', label: 'Main House', status: 'active' },
      {
        id: PROVIDER,
        entity_type: 'provider',
        label: 'ABC Electric',
        status: 'active',
      },
    ],
    edges: [{ source: HOUSEHOLD, target: PROVIDER, type: 'USES_PROVIDER' }],
  })
  vi.mocked(worldApi.entity).mockResolvedValue(detail())
  vi.mocked(worldApi.history).mockResolvedValue({
    entity_id: HOUSEHOLD,
    fact_history: [],
    memories: [],
    covers: [
      'every version of every fact this entity has carried',
      'memories referencing this entity, including closed versions',
    ],
  })
  vi.mocked(worldApi.unlink).mockResolvedValue(undefined)
  vi.mocked(worldApi.link).mockResolvedValue({
    source: PERSON,
    target: HOUSEHOLD,
    type: 'MEMBER_OF',
  })
  vi.mocked(preferencesApi.history).mockResolvedValue({
    key: 'scheduling.earliest',
    history: [],
    total: 0,
  })
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('the graph', () => {
  it('renders the entities and relationships the API returned', async () => {
    renderPage()
    expect(await screen.findByText('node:Gene')).toBeInTheDocument()
    expect(screen.getByText('node:Main House')).toBeInTheDocument()
    expect(
      screen.getByText(`edge:${PERSON}-MEMBER_OF-${HOUSEHOLD}`),
    ).toBeInTheDocument()
  })

  it('sends the entity-type filter as an array, not a joined string', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('node:Gene')

    await user.click(screen.getByRole('button', { name: 'Household' }))

    await waitFor(() => {
      expect(worldApi.graph).toHaveBeenLastCalledWith(
        expect.objectContaining({ types: ['household'] }),
      )
    })
  })

  it('expands a clicked node with its neighborhood', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByText('node:Main House'))

    expect(worldApi.neighborhood).toHaveBeenCalledWith(HOUSEHOLD, 1)
    expect(await screen.findByText('node:ABC Electric')).toBeInTheDocument()
  })
})

describe('the entity inspector', () => {
  it('shows facts, the named relationship, and provenance', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByText('node:Main House'))

    const panel = await screen.findByRole('complementary', {
      name: /Entity inspector: Main House/,
    })
    expect(within(panel).getByText('address')).toBeInTheDocument()
    expect(within(panel).getByText('12 Elm Street')).toBeInTheDocument()
    // The far endpoint arrives as an id and is rendered with its label.
    expect(within(panel).getByRole('button', { name: 'Gene' })).toBeInTheDocument()
    expect(within(panel).getByText('lifeops-console')).toBeInTheDocument()
  })

  it('states what the history covers so an empty list is not read as silence', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByText('node:Main House'))

    expect(
      await screen.findByText(/Covers memories referencing this entity/),
    ).toBeInTheDocument()
  })

  it('shows related tasks and memories when the server sends them', async () => {
    vi.mocked(worldApi.entity).mockResolvedValue(
      detail({
        related_tasks: [{ id: 'task_1', title: 'Oil change', state: 'CAPTURED' } as Task],
        related_memories: [
          {
            id: 'memory_1',
            content: 'The house was rewired in 2024',
            valid_to: null,
            created_at: '2026-08-16T10:00:00Z',
          } as MemoryRecord,
        ],
      }),
    )
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByText('node:Main House'))

    expect(await screen.findByText('Oil change')).toBeInTheDocument()
    expect(screen.getByText('The house was rewired in 2024')).toBeInTheDocument()
  })

  it('unlinks using the edge direction the server stored', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByText('node:Main House'))
    await user.click(
      await screen.findByRole('button', {
        name: /Remove MEMBER_OF relationship with Gene/,
      }),
    )

    // The edge is person → household, so it must be sent that way even though
    // the household is the entity being inspected.
    await waitFor(() => {
      expect(worldApi.unlink).toHaveBeenCalledWith({
        source_id: PERSON,
        target_id: HOUSEHOLD,
        rel_type: 'MEMBER_OF',
      })
    })
  })
})

describe('domain operations', () => {
  it('creates an entity through the dialog and refetches the graph', async () => {
    vi.mocked(worldApi.createEntity).mockResolvedValue({
      id: PROVIDER,
      entity_type: 'provider',
      display_name: 'ABC Electric',
      facts: {},
      created_at: '2026-08-16T10:00:00Z',
      updated_at: '2026-08-16T10:00:00Z',
      created_by_client: 'lifeops-console',
    })
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('node:Gene')

    await user.click(screen.getByRole('button', { name: /Add entity/ }))
    await user.type(screen.getByLabelText(/Name/i), 'ABC Electric')
    await user.click(screen.getByRole('button', { name: /^Create$/ }))

    await waitFor(() => {
      expect(worldApi.createEntity).toHaveBeenCalledWith(
        expect.objectContaining({ display_name: 'ABC Electric' }),
      )
    })
    // A created entity that never reappears is the bug this guards.
    await waitFor(() => {
      expect(vi.mocked(worldApi.graph).mock.calls.length).toBeGreaterThan(1)
    })
  })

  it('links two entities using rel_type', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('node:Gene')

    await user.click(screen.getByRole('button', { name: /Link entities/ }))
    await user.selectOptions(screen.getByLabelText('From'), PERSON)
    await user.selectOptions(screen.getByLabelText('Relationship type'), 'MEMBER_OF')
    await user.selectOptions(screen.getByLabelText('To'), HOUSEHOLD)
    await user.click(screen.getByRole('button', { name: /^Link$/ }))

    await waitFor(() => {
      expect(worldApi.link).toHaveBeenCalledWith({
        source_id: PERSON,
        target_id: HOUSEHOLD,
        rel_type: 'MEMBER_OF',
      })
    })
  })

  it('offers the whole BUILD_SPEC section 39 vocabulary, in the spec order', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('node:Gene')

    await user.click(screen.getByRole('button', { name: /Link entities/ }))

    const select = screen.getByLabelText('Relationship type')
    const offered = within(select)
      .getAllByRole('option')
      .map((option) => (option as HTMLOptionElement).value)
      .filter(Boolean)
    // Pinned literally: silently dropping a type the spec defines is the
    // regression this guards, and the picker must not drift from the server.
    expect(offered).toEqual([
      'MEMBER_OF',
      'RELATED_TO',
      'PREFERS',
      'OWNS',
      'USES_PROVIDER',
      'ASSIGNED_TO',
      'ABOUT',
      'WITH_PROVIDER',
      'FOR_ASSET',
      'WAITING_ON',
      'REQUIRES_APPROVAL',
      'AUTHORIZES',
      'CREATED_BY',
      'REQUESTED_BY',
      'EXECUTED_BY',
      'VERIFIED_BY',
      'DERIVED_FROM',
      'SUPERSEDES',
      'RELATED_MEMORY',
      'REFERENCES',
    ])
  })
})

describe('the section 15 temporal/current toggle', () => {
  const PREFERENCE = 'preference_01'

  function preferenceGraph(): WorldGraph {
    return {
      nodes: [
        { id: PERSON, entity_type: 'person', label: 'Gene', status: 'active' },
        {
          id: PREFERENCE,
          entity_type: 'preference',
          label: 'nothing before ten',
          status: 'active',
        },
      ],
      edges: [{ source: PERSON, target: PREFERENCE, type: 'PREFERS' }],
    }
  }

  function preferenceDetail(): WorldEntityDetail {
    return {
      entity: {
        id: PREFERENCE,
        entity_type: 'preference',
        display_name: 'nothing before ten',
        facts: { key: 'scheduling.earliest', source: 'user_explicit' },
        created_at: '2026-08-16T10:00:00Z',
        updated_at: '2026-08-16T10:00:00Z',
        created_by_client: 'hermes-personal',
      },
      relationships: [{ source: PERSON, target: PREFERENCE, type: 'PREFERS' }],
      neighbors: [{ id: PERSON, entity_type: 'person', label: 'Gene', status: 'active' }],
      related_tasks: [],
      related_memories: [],
    }
  }

  it('shows current facts by default', async () => {
    vi.mocked(worldApi.graph).mockResolvedValue(preferenceGraph())
    vi.mocked(worldApi.entity).mockResolvedValue(preferenceDetail())
    renderPage()

    await userEvent.click(await screen.findByText('node:nothing before ten'))
    expect(await screen.findByText('Current facts')).toBeInTheDocument()
    expect(screen.queryByText('Preference history')).not.toBeInTheDocument()
  })

  it('switches to preference history in History mode', async () => {
    vi.mocked(worldApi.graph).mockResolvedValue(preferenceGraph())
    vi.mocked(worldApi.entity).mockResolvedValue(preferenceDetail())
    vi.mocked(preferencesApi.history).mockResolvedValue({
      key: 'scheduling.earliest',
      history: [
        {
          id: 'pref_current',
          subject_id: PERSON,
          key: 'scheduling.earliest',
          value: 'nothing before ten',
          source_type: 'user_explicit',
          source_id: null,
          confidence: 1,
          importance: 0.5,
          observed_at: '2026-08-16T10:00:00Z',
          created_at: '2026-08-16T10:00:00Z',
          valid_from: '2026-08-16T10:00:00Z',
          valid_to: null,
          supersedes: 'pref_old',
          created_by_client: 'hermes-personal',
          notes: null,
          is_current: true,
        },
        {
          id: 'pref_old',
          subject_id: PERSON,
          key: 'scheduling.earliest',
          value: 'nothing before nine',
          source_type: 'user_explicit',
          source_id: null,
          confidence: 1,
          importance: 0.5,
          observed_at: '2026-08-01T10:00:00Z',
          created_at: '2026-08-01T10:00:00Z',
          valid_from: '2026-08-01T10:00:00Z',
          valid_to: '2026-08-16T10:00:00Z',
          supersedes: null,
          created_by_client: 'hermes-personal',
          notes: null,
          is_current: false,
        },
      ],
      total: 2,
    })
    renderPage()

    await userEvent.click(await screen.findByText('node:nothing before ten'))
    await screen.findByText('Current facts')

    await userEvent.click(screen.getByRole('button', { name: /history/i }))

    expect(await screen.findByText('Preference history')).toBeInTheDocument()
    // "nothing before ten" also appears in the header (it's the display
    // name); the point under test is that the history entry renders too.
    expect(screen.getAllByText('nothing before ten').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('nothing before nine')).toBeInTheDocument()
    await waitFor(() =>
      expect(preferencesApi.history).toHaveBeenCalledWith('scheduling.earliest'),
    )
  })

  it('tells a non-preference entity it has no fact history yet', async () => {
    renderPage()
    await userEvent.click(await screen.findByText('node:Main House'))
    await screen.findByText('Current facts')

    await userEvent.click(screen.getByRole('button', { name: /history/i }))

    expect(
      await screen.findByText(/no recorded changes to this entity's facts/i),
    ).toBeInTheDocument()
    expect(preferencesApi.history).not.toHaveBeenCalled()
  })

  it('shows a non-preference entity its per-fact history, grouped by key', async () => {
    vi.mocked(worldApi.history).mockResolvedValue({
      entity_id: HOUSEHOLD,
      fact_history: [
        {
          id: 'fact_phone_2',
          entity_id: HOUSEHOLD,
          key: 'phone',
          value: '555-9999',
          valid_from: '2026-02-01T00:00:00Z',
          valid_to: null,
          supersedes: 'fact_phone_1',
          created_by_client: 'hermes-personal',
        },
        {
          id: 'fact_phone_1',
          entity_id: HOUSEHOLD,
          key: 'phone',
          value: '555-0100',
          valid_from: '2026-01-01T00:00:00Z',
          valid_to: '2026-02-01T00:00:00Z',
          supersedes: null,
          created_by_client: 'hermes-personal',
        },
      ],
      memories: [],
      covers: ['every version of every fact this entity has carried'],
    })
    renderPage()
    await userEvent.click(await screen.findByText('node:Main House'))
    await screen.findByText('Current facts')

    await userEvent.click(screen.getByRole('button', { name: /history/i }))

    expect(await screen.findByText('Fact history')).toBeInTheDocument()
    expect(screen.getByText('phone')).toBeInTheDocument()
    expect(screen.getByText('555-9999')).toBeInTheDocument()
    expect(screen.getByText('555-0100')).toBeInTheDocument()
  })
})
