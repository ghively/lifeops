import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TasksPage } from '../TasksPage'
import { tasksApi, objectsApi, type TaskItem } from '@/services/api'

// TasksPage uses tasksApi.list for listing (with filters) and
// objectsApi.create for creating new tasks.
vi.mock('@/services/api', () => ({
  tasksApi: {
    list: vi.fn(),
    get: vi.fn(),
    assign: vi.fn(),
    updateStatus: vi.fn(),
  },
  objectsApi: {
    list: vi.fn(),
    create: vi.fn(),
  },
}))

// TaskAssignmentDialog renders nothing of interest here; stub it.
vi.mock('@/components/tasks/TaskAssignmentDialog', () => ({
  TaskAssignmentDialog: () => null,
}))

const mockTasksApi = tasksApi as any
const mockObjectsApi = objectsApi as any

const mockTasks: TaskItem[] = [
  {
    id: 'task-1',
    type: 'task',
    title: 'Task 1',
    properties: { status: 'todo', priority: 'high' },
  } as any,
  {
    id: 'task-2',
    type: 'task',
    title: 'Task 2',
    properties: { status: 'in-progress', priority: 'medium' },
  } as any,
  {
    id: 'task-3',
    type: 'task',
    title: 'Task 3',
    properties: { status: 'done', priority: 'low' },
  } as any,
]

describe('TasksPage', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    vi.clearAllMocks()
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: 0, staleTime: 0 },
        mutations: { retry: false },
      },
    })
    mockTasksApi.list.mockResolvedValue({
      tasks: mockTasks,
      by_status: { todo: 1, 'in-progress': 1, done: 1 },
      by_priority: { high: 1, medium: 1, low: 1 },
    })
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

  it('renders tasks heading after load', async () => {
    renderPage()

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /Tasks/i, level: 1 })).toBeInTheDocument()
    })
  })

  it('displays pulse loading placeholder initially', async () => {
    mockTasksApi.list.mockImplementation(
      () => new Promise((resolve) => {
        setTimeout(() => resolve({
          tasks: mockTasks,
          by_status: {},
          by_priority: {},
        }), 50)
      })
    )

    const { container } = renderPage()

    await waitFor(() => {
      expect(container.querySelector('.animate-pulse')).toBeInTheDocument()
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

  it('filters by status via Done filter button', async () => {
    const user = userEvent.setup()
    renderPage()

    await screen.findByText('Task 1')

    // Status filters are buttons labeled like "Done (N)".
    const doneFilter = await screen.findByRole('button', { name: /^Done \(/i })
    await user.click(doneFilter)

    await waitFor(() => {
      expect(mockTasksApi.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: 'done' })
      )
    })
  })

  it('filters by priority via high button', async () => {
    const user = userEvent.setup()
    renderPage()

    await screen.findByText('Task 1')

    // Priority filter buttons are labelled "high (N)" etc (lowercase).
    const highFilter = await screen.findByRole('button', { name: /^high \(/i })
    await user.click(highFilter)

    await waitFor(() => {
      expect(mockTasksApi.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ priority: 'high' })
      )
    })
  })

  it('creates a task via the New Task header button', async () => {
    const user = userEvent.setup()
    mockObjectsApi.create.mockResolvedValue({
      id: 'task-new',
      type: 'task',
      title: 'New Task',
      properties: { status: 'todo', priority: 'medium' },
    })

    renderPage()

    await screen.findByText('Task 1')

    const newTaskButton = await screen.findByRole('button', { name: /^New Task$/i })
    await user.click(newTaskButton)

    await waitFor(() => {
      expect(mockObjectsApi.create).toHaveBeenCalled()
    })
  })

  it('creates a task inline via the Add button', async () => {
    const user = userEvent.setup()
    mockObjectsApi.create.mockResolvedValue({
      id: 'task-new',
      type: 'task',
      title: 'Inline Task',
      properties: { status: 'todo', priority: 'medium' },
    })

    renderPage()

    await screen.findByText('Task 1')

    const inlineInput = screen.getByPlaceholderText(/Create a task inline/i)
    await user.type(inlineInput, 'Inline Task')

    const addButton = await screen.findByRole('button', { name: /^Add$/i })
    await user.click(addButton)

    await waitFor(() => {
      expect(mockObjectsApi.create).toHaveBeenCalled()
    })
  })

  it('displays error on API failure', async () => {
    mockTasksApi.list.mockRejectedValue(new Error('API Error'))

    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/Failed to load tasks/i)).toBeInTheDocument()
    })
  })

  it('disables inline Add button while creating', async () => {
    mockObjectsApi.create.mockImplementation(
      () => new Promise((resolve) => {
        setTimeout(() => resolve({
          id: 'task-new',
          type: 'task',
          title: 'Pending Task',
          properties: {},
        }), 100)
      })
    )

    const user = userEvent.setup()
    renderPage()

    await screen.findByText('Task 1')

    const inlineInput = screen.getByPlaceholderText(/Create a task inline/i)
    await user.type(inlineInput, 'Pending Task')

    const addButton = await screen.findByRole('button', { name: /^Add$/i })
    await user.click(addButton)

    await waitFor(() => {
      expect(addButton).toBeDisabled()
    })
  })

  it('shows all tasks when the All filter is clicked', async () => {
    const user = userEvent.setup()
    renderPage()

    await screen.findByText('Task 1')

    // Two filter rows each have an "All" button (status + priority). Any
    // click should not trigger errors and should re-render with all tasks.
    const allButtons = await screen.findAllByRole('button', { name: /All/i })
    expect(allButtons.length).toBeGreaterThan(0)
    await user.click(allButtons[0])

    expect(screen.getByText('Task 1')).toBeInTheDocument()
    expect(screen.getByText('Task 2')).toBeInTheDocument()
    expect(screen.getByText('Task 3')).toBeInTheDocument()
  })

  it('displays task priority and status text', async () => {
    renderPage()

    await screen.findByText('Task 1')

    // Priority labels appear alongside task titles.
    expect(screen.getAllByText(/high/i).length).toBeGreaterThan(0)
    // Status label "To Do" from statusLabels map
    expect(screen.getByText('To Do')).toBeInTheDocument()
  })

  it('shows empty state when there are no tasks', async () => {
    mockTasksApi.list.mockResolvedValue({
      tasks: [],
      by_status: {},
      by_priority: {},
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/No tasks found/i)).toBeInTheDocument()
    })
  })
})
