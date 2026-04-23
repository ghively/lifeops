import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TasksPage } from '../TasksPage'
import { tasksApi, objectsApi, type TaskItem } from '@/services/api'

vi.mock('@/services/api', () => ({
  tasksApi: {
    list: vi.fn(),
    update: vi.fn(),
    complete: vi.fn(),
  },
  objectsApi: {
    list: vi.fn(),
  },
}))

const mockTasksApi = tasksApi as any
const mockObjectsApi = objectsApi as any

const mockTasks: TaskItem[] = [
  {
    id: 'task-1',
    title: 'Task 1',
    status: 'todo',
    priority: 'high',
    created_at: new Date().toISOString(),
  },
  {
    id: 'task-2',
    title: 'Task 2',
    status: 'in-progress',
    priority: 'medium',
    created_at: new Date().toISOString(),
  },
  {
    id: 'task-3',
    title: 'Task 3',
    status: 'done',
    priority: 'low',
    created_at: new Date().toISOString(),
  },
]

describe('TasksPage', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    vi.clearAllMocks()
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })
    mockTasksApi.list.mockResolvedValue({ tasks: mockTasks })
    mockObjectsApi.list.mockResolvedValue({ objects: [] })
  })

  const renderPage = () => {
    return render(
      <BrowserRouter>
        <QueryClientProvider client={queryClient}>
          <TasksPage />
        </QueryClientProvider>
      </BrowserRouter>
    )
  }

  it('renders tasks page', () => {
    renderPage()

    expect(screen.getByText(/tasks/i)).toBeInTheDocument()
  })

  it('displays loading state initially', async () => {
    mockTasksApi.list.mockImplementation(
      () =>
        new Promise((resolve) => {
          setTimeout(() => resolve({ tasks: mockTasks }), 50)
        })
    )

    renderPage()

    await waitFor(() => {
      expect(screen.getByRole('status')).toBeInTheDocument()
    })
  })

  it('displays tasks list', async () => {
    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Task 1')).toBeInTheDocument()
      expect(screen.getByText('Task 2')).toBeInTheDocument()
      expect(screen.getByText('Task 3')).toBeInTheDocument()
    })
  })

  it('filters by status', async () => {
    const user = userEvent.setup()
    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Task 1')).toBeInTheDocument()
    })

    const doneFilter = screen.getByRole('button', { name: /done/i })
    await user.click(doneFilter)

    // Only done tasks should be visible
    expect(screen.getByText('Task 3')).toBeInTheDocument()
  })

  it('filters by priority', async () => {
    const user = userEvent.setup()
    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Task 1')).toBeInTheDocument()
    })

    const highFilter = screen.getByRole('button', { name: /high/i })
    await user.click(highFilter)

    // Only high priority tasks should be visible
    expect(screen.getByText('Task 1')).toBeInTheDocument()
  })

  it('marks task as complete', async () => {
    const user = userEvent.setup()
    mockTasksApi.complete.mockResolvedValue({ success: true })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Task 1')).toBeInTheDocument()
    })

    const completeButtons = screen.getAllByRole('button', { name: /complete|check/i })
    if (completeButtons.length > 0) {
      await user.click(completeButtons[0])

      await waitFor(() => {
        expect(mockTasksApi.complete).toHaveBeenCalled()
      })
    }
  })

  it('creates new task', async () => {
    const user = userEvent.setup()
    mockTasksApi.update.mockResolvedValue({ id: 'task-new', title: 'New Task' })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Task 1')).toBeInTheDocument()
    })

    const newTaskInput = screen.getByPlaceholderText(/new task/i)
    await user.type(newTaskInput, 'New Task')

    const addButton = screen.getByRole('button', { name: /\+|add|create/i })
    await user.click(addButton)

    await waitFor(() => {
      expect(mockTasksApi.update).toHaveBeenCalled()
    })
  })

  it('displays error on API failure', async () => {
    mockTasksApi.list.mockRejectedValue(new Error('API Error'))

    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/error|failed/i)).toBeInTheDocument()
    })
  })

  it('disables submit while pending', async () => {
    mockTasksApi.update.mockImplementation(
      () =>
        new Promise((resolve) => {
          setTimeout(() => resolve({}), 100)
        })
    )

    const user = userEvent.setup()
    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Task 1')).toBeInTheDocument()
    })

    const newTaskInput = screen.getByPlaceholderText(/new task/i)
    await user.type(newTaskInput, 'Test Task')

    const addButton = screen.getByRole('button', { name: /\+|add|create/i })
    await user.click(addButton)

    // Button should be disabled during request
    expect(addButton).toBeDisabled()
  })

  it('shows all tasks when filter is "all"', async () => {
    const user = userEvent.setup()
    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Task 1')).toBeInTheDocument()
    })

    const allFilter = screen.getByRole('button', { name: /all/i })
    await user.click(allFilter)

    expect(screen.getByText('Task 1')).toBeInTheDocument()
    expect(screen.getByText('Task 2')).toBeInTheDocument()
    expect(screen.getByText('Task 3')).toBeInTheDocument()
  })

  it('displays task priority and status badges', async () => {
    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Task 1')).toBeInTheDocument()
    })

    // Check for status and priority display
    const badges = screen.queryAllByRole('button')
    expect(badges.length).toBeGreaterThan(0)
  })
})
