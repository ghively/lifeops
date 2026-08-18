/**
 * Routines screen behaviour (BUILD_SPEC sections 73, 100).
 *
 * Pins what LifeOps Core decides and this screen only renders/submits: steps,
 * trigger, next run, and enabled state come straight from the server;
 * creating, revising (by name), and deleting all go through the same save
 * and delete calls the server validates.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { RoutinesPage } from '../RoutinesPage'
import { workflowTemplatesApi, type WorkflowTemplate } from '@/services/lifeops'

vi.mock('@/services/lifeops', async () => {
  const actual = await vi.importActual<typeof import('@/services/lifeops')>(
    '@/services/lifeops',
  )
  return {
    ...actual,
    workflowTemplatesApi: {
      list: vi.fn(),
      due: vi.fn(),
      save: vi.fn(),
      delete: vi.fn(),
    },
  }
})

function makeTemplate(overrides: Partial<WorkflowTemplate> = {}): WorkflowTemplate {
  return {
    id: 'template_weekly_review',
    name: 'Weekly review',
    description: 'Look back on the week',
    steps: [
      { order: 0, description: 'Summarize tasks', action_type: null },
      { order: 1, description: 'Send digest', action_type: 'send_email' },
    ],
    trigger: 'manual',
    next_run_at: null,
    enabled: true,
    created_at: '2026-08-10T08:00:00Z',
    updated_at: '2026-08-10T08:00:00Z',
    created_by_client: 'lifeops-console',
    ...overrides,
  }
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <RoutinesPage />
    </QueryClientProvider>,
  )
}

const mockedTemplates = vi.mocked(workflowTemplatesApi)

beforeEach(() => {
  mockedTemplates.list.mockResolvedValue({ templates: [makeTemplate()], total: 1 })
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('Routines', () => {
  it('renders steps, trigger, and enabled state from the server', async () => {
    renderPage()
    expect(await screen.findByText('Weekly review')).toBeInTheDocument()
    expect(screen.getByText('Summarize tasks')).toBeInTheDocument()
    expect(screen.getByText('Send digest')).toBeInTheDocument()
    expect(screen.getByText('(send_email)')).toBeInTheDocument()
    expect(screen.getByText('Manual')).toBeInTheDocument()
    expect(screen.getByText('Enabled')).toBeInTheDocument()
  })

  it('shows a disabled template honestly', async () => {
    mockedTemplates.list.mockResolvedValue({
      templates: [makeTemplate({ enabled: false })],
      total: 1,
    })
    renderPage()
    expect(await screen.findByText('Disabled')).toBeInTheDocument()
  })

  it('carries a paused routine through a revision', async () => {
    // The server rebuilds the template from this payload, so omitting
    // `enabled` would switch a paused routine back on — and the user who
    // paused it would not be told.
    mockedTemplates.list.mockResolvedValue({
      templates: [makeTemplate({ name: 'Weekly review', enabled: false })],
      total: 1,
    })
    mockedTemplates.save.mockResolvedValue(makeTemplate({ enabled: false }))
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: /revise/i }))
    await userEvent.click(screen.getByRole('button', { name: /save revision/i }))

    await waitFor(() => {
      expect(mockedTemplates.save).toHaveBeenCalledWith(
        expect.objectContaining({ enabled: false }),
      )
    })
  })

  it('creates a routine with a step', async () => {
    mockedTemplates.save.mockResolvedValue(makeTemplate({ name: 'Nightly backup check' }))
    renderPage()
    await screen.findByText('Weekly review')

    await userEvent.click(screen.getByRole('button', { name: /new routine/i }))
    await userEvent.type(screen.getByLabelText('Name'), 'Nightly backup check')
    await userEvent.click(screen.getByRole('button', { name: /add step/i }))
    await userEvent.type(screen.getByLabelText('Step 1 description'), 'Check backup log')

    await userEvent.click(screen.getByRole('button', { name: /^create$/i }))

    await waitFor(() =>
      expect(mockedTemplates.save).toHaveBeenCalledWith({
        enabled: true,
        name: 'Nightly backup check',
        description: undefined,
        steps: [{ order: 0, description: 'Check backup log', action_type: null }],
        trigger: 'manual',
        next_run_at: undefined,
      }),
    )
  })

  it('refuses to submit a scheduled routine with no run time', async () => {
    renderPage()
    await screen.findByText('Weekly review')

    await userEvent.click(screen.getByRole('button', { name: /new routine/i }))
    await userEvent.type(screen.getByLabelText('Name'), 'Nightly backup check')
    await userEvent.selectOptions(screen.getByLabelText('Trigger'), 'schedule')

    expect(screen.getByRole('button', { name: /^create$/i })).toBeDisabled()
    expect(
      screen.getByText(/a scheduled routine needs a next run time/i),
    ).toBeInTheDocument()
  })

  it('revising opens the same dialog pre-filled, keyed by name', async () => {
    renderPage()
    await screen.findByText('Weekly review')

    await userEvent.click(screen.getByRole('button', { name: /revise/i }))

    expect(screen.getByText('Revise Weekly review')).toBeInTheDocument()
    expect(screen.getByLabelText('Name')).toHaveValue('Weekly review')
    expect(screen.getByLabelText('Name')).toBeDisabled()
    expect(screen.getByLabelText('Step 1 description')).toHaveValue('Summarize tasks')

    mockedTemplates.save.mockResolvedValue(makeTemplate({ description: 'Revised' }))
    await userEvent.clear(screen.getByLabelText('Description (optional)'))
    await userEvent.type(screen.getByLabelText('Description (optional)'), 'Revised')
    await userEvent.click(screen.getByRole('button', { name: /save revision/i }))

    await waitFor(() =>
      expect(mockedTemplates.save).toHaveBeenCalledWith(
        expect.objectContaining({ name: 'Weekly review', description: 'Revised' }),
      ),
    )
  })

  it('deletes a routine after confirmation', async () => {
    mockedTemplates.delete.mockResolvedValue(undefined)
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderPage()
    await screen.findByText('Weekly review')

    await userEvent.click(screen.getByRole('button', { name: 'Delete Weekly review' }))

    await waitFor(() =>
      expect(mockedTemplates.delete).toHaveBeenCalledWith('template_weekly_review'),
    )
  })

  it('a cancelled confirmation deletes nothing', async () => {
    mockedTemplates.delete.mockResolvedValue(undefined)
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    renderPage()
    await screen.findByText('Weekly review')

    await userEvent.click(screen.getByRole('button', { name: 'Delete Weekly review' }))

    expect(mockedTemplates.delete).not.toHaveBeenCalled()
  })

  it('has an honest empty state', async () => {
    mockedTemplates.list.mockResolvedValue({ templates: [], total: 0 })
    renderPage()
    expect(await screen.findByText('No routines yet.')).toBeInTheDocument()
  })

  it('explains an unreachable LifeOps Core rather than showing a bare error', async () => {
    mockedTemplates.list.mockRejectedValue(new Error('Network Error'))
    renderPage()
    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument()
  })
})
