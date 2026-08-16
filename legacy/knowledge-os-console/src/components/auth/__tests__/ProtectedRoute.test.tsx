import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ProtectedRoute } from '../ProtectedRoute'
import { useAuthStore } from '@/stores/auth'

// Mock the auth store
vi.mock('@/stores/auth', () => ({
  useAuthStore: vi.fn(),
}))

const mockAuthStore = useAuthStore as any

describe('ProtectedRoute', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders children when authenticated', () => {
    mockAuthStore.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      isInitialized: true,
    })

    render(
      <MemoryRouter initialEntries={['/protected']}>
        <Routes>
          <Route
            path="/protected"
            element={
              <ProtectedRoute>
                <div>Protected content</div>
              </ProtectedRoute>
            }
          />
        </Routes>
      </MemoryRouter>
    )

    expect(screen.getByText('Protected content')).toBeInTheDocument()
  })

  it('redirects to /login when not authenticated', () => {
    mockAuthStore.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      isInitialized: true,
    })

    render(
      <MemoryRouter initialEntries={['/protected']}>
        <Routes>
          <Route
            path="/protected"
            element={
              <ProtectedRoute>
                <div>Protected content</div>
              </ProtectedRoute>
            }
          />
          <Route path="/login" element={<div>Login page</div>} />
        </Routes>
      </MemoryRouter>
    )

    expect(screen.getByText('Login page')).toBeInTheDocument()
    expect(screen.queryByText('Protected content')).not.toBeInTheDocument()
  })

  it('shows spinner when isLoading is true', () => {
    mockAuthStore.mockReturnValue({
      isAuthenticated: true,
      isLoading: true,
      isInitialized: false,
    })

    render(
      <MemoryRouter initialEntries={['/protected']}>
        <Routes>
          <Route
            path="/protected"
            element={
              <ProtectedRoute>
                <div>Protected content</div>
              </ProtectedRoute>
            }
          />
        </Routes>
      </MemoryRouter>
    )

    expect(screen.queryByText('Protected content')).not.toBeInTheDocument()
    // Check that loader is rendered (by checking the container has a spinner SVG)
    expect(document.querySelector('svg')?.classList.contains('animate-spin')).toBe(true)
  })

  it('shows spinner when not initialized', () => {
    mockAuthStore.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      isInitialized: false,
    })

    render(
      <MemoryRouter initialEntries={['/protected']}>
        <Routes>
          <Route
            path="/protected"
            element={
              <ProtectedRoute>
                <div>Protected content</div>
              </ProtectedRoute>
            }
          />
        </Routes>
      </MemoryRouter>
    )

    expect(screen.queryByText('Protected content')).not.toBeInTheDocument()
    expect(document.querySelector('svg')?.classList.contains('animate-spin')).toBe(true)
  })

  it('prioritizes initialization check over auth check', () => {
    mockAuthStore.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      isInitialized: false,
    })

    render(
      <MemoryRouter initialEntries={['/protected']}>
        <Routes>
          <Route
            path="/protected"
            element={
              <ProtectedRoute>
                <div>Protected content</div>
              </ProtectedRoute>
            }
          />
          <Route path="/login" element={<div>Login page</div>} />
        </Routes>
      </MemoryRouter>
    )

    // Should show spinner, not redirect
    expect(document.querySelector('svg')?.classList.contains('animate-spin')).toBe(true)
    expect(screen.queryByText('Login page')).not.toBeInTheDocument()
  })

  it('renders multiple children nodes', () => {
    mockAuthStore.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      isInitialized: true,
    })

    render(
      <MemoryRouter initialEntries={['/protected']}>
        <Routes>
          <Route
            path="/protected"
            element={
              <ProtectedRoute>
                <div>Content 1</div>
                <div>Content 2</div>
              </ProtectedRoute>
            }
          />
        </Routes>
      </MemoryRouter>
    )

    expect(screen.getByText('Content 1')).toBeInTheDocument()
    expect(screen.getByText('Content 2')).toBeInTheDocument()
  })
})
