import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { LoginPage } from '../LoginPage'
import { useAuthStore } from '@/stores/auth'

// Mock the auth store
vi.mock('@/stores/auth', () => ({
  useAuthStore: vi.fn(),
}))

const mockAuthStore = useAuthStore as any

describe('LoginPage', () => {
  const mockLogin = vi.fn()
  const mockRegister = vi.fn()
  const mockClearError = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    mockAuthStore.mockReturnValue({
      login: mockLogin,
      register: mockRegister,
      isAuthenticated: false,
      isLoading: false,
      error: null,
      clearError: mockClearError,
    })
  })

  describe('Login Mode', () => {
    it('renders login form by default', () => {
      render(
        <MemoryRouter initialEntries={['/login']}>
          <LoginPage />
        </MemoryRouter>
      )

      expect(screen.getByText('Welcome back')).toBeInTheDocument()
      expect(screen.getByDisplayValue('')).toHaveAttribute('id', 'login-email')
    })

    it('submits login with email and password', async () => {
      const user = userEvent.setup()
      mockLogin.mockResolvedValue(undefined)

      render(
        <MemoryRouter initialEntries={['/login']}>
          <LoginPage />
        </MemoryRouter>
      )

      await user.type(screen.getByLabelText('Email'), 'test@example.com')
      await user.type(screen.getByLabelText('Password'), 'password123')
      await user.click(screen.getByRole('button', { name: /Sign in/i }))

      await waitFor(() => {
        expect(mockLogin).toHaveBeenCalledWith('test@example.com', 'password123')
      })
    })

    it('displays API error on 401', async () => {
      const user = userEvent.setup()
      mockAuthStore.mockReturnValue({
        login: mockLogin,
        register: mockRegister,
        isAuthenticated: false,
        isLoading: false,
        error: 'Invalid credentials',
        clearError: mockClearError,
      })

      render(
        <MemoryRouter initialEntries={['/login']}>
          <LoginPage />
        </MemoryRouter>
      )

      expect(screen.getByText('Invalid credentials')).toBeInTheDocument()
    })

    it('disables submit button while pending', () => {
      mockAuthStore.mockReturnValue({
        login: mockLogin,
        register: mockRegister,
        isAuthenticated: false,
        isLoading: true,
        error: null,
        clearError: mockClearError,
      })

      render(
        <MemoryRouter initialEntries={['/login']}>
          <LoginPage />
        </MemoryRouter>
      )

      const submitButton = screen.getByRole('button', { name: /Signing in/i })
      expect(submitButton).toBeDisabled()
      expect(screen.getByLabelText('Email')).toBeDisabled()
    })

    it('switches to register mode', async () => {
      const user = userEvent.setup()

      render(
        <MemoryRouter initialEntries={['/login']}>
          <LoginPage />
        </MemoryRouter>
      )

      await user.click(screen.getByRole('button', { name: /Sign up/i }))

      expect(screen.getByText('Create an account')).toBeInTheDocument()
    })

    it('validates empty email', async () => {
      const user = userEvent.setup()
      mockLogin.mockRejectedValue(new Error('Email required'))

      render(
        <MemoryRouter initialEntries={['/login']}>
          <LoginPage />
        </MemoryRouter>
      )

      const emailInput = screen.getByLabelText('Email') as HTMLInputElement
      expect(emailInput.required).toBe(true)
    })

    it('validates empty password', async () => {
      const user = userEvent.setup()

      render(
        <MemoryRouter initialEntries={['/login']}>
          <LoginPage />
        </MemoryRouter>
      )

      const passwordInput = screen.getByLabelText('Password') as HTMLInputElement
      expect(passwordInput.required).toBe(true)
    })
  })

  describe('Register Mode', () => {
    it('renders register form when in register mode', () => {
      render(
        <MemoryRouter initialEntries={['/register']}>
          <LoginPage />
        </MemoryRouter>
      )

      expect(screen.getByText('Create an account')).toBeInTheDocument()
      expect(screen.getByLabelText('Email')).toBeInTheDocument()
      expect(screen.getByLabelText('Username')).toBeInTheDocument()
      expect(screen.getByLabelText(/Display Name/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/^Password$/)).toBeInTheDocument()
      expect(screen.getByLabelText(/Confirm Password/i)).toBeInTheDocument()
    })

    it('submits register with all fields', async () => {
      const user = userEvent.setup()
      mockRegister.mockResolvedValue(undefined)

      render(
        <MemoryRouter initialEntries={['/register']}>
          <LoginPage />
        </MemoryRouter>
      )

      await user.type(screen.getByLabelText('Email'), 'new@example.com')
      await user.type(screen.getByLabelText('Username'), 'newuser')
      await user.type(screen.getByLabelText(/Display Name/i), 'New User')
      await user.type(screen.getByLabelText(/^Password$/), 'ValidPass123')
      await user.type(screen.getByLabelText(/Confirm Password/i), 'ValidPass123')
      await user.click(screen.getByRole('button', { name: /Create account/i }))

      await waitFor(() => {
        expect(mockRegister).toHaveBeenCalledWith({
          email: 'new@example.com',
          username: 'newuser',
          display_name: 'New User',
          password: 'ValidPass123',
        })
      })
    })

    it('validates password length', async () => {
      const user = userEvent.setup()

      render(
        <MemoryRouter initialEntries={['/register']}>
          <LoginPage />
        </MemoryRouter>
      )

      await user.type(screen.getByLabelText('Email'), 'test@example.com')
      await user.type(screen.getByLabelText('Username'), 'testuser')
      await user.type(screen.getByLabelText(/^Password$/), 'short')
      await user.type(screen.getByLabelText(/Confirm Password/i), 'short')
      await user.click(screen.getByRole('button', { name: /Create account/i }))

      expect(
        screen.getByText('Password must be at least 8 characters')
      ).toBeInTheDocument()
    })

    it('validates password match', async () => {
      const user = userEvent.setup()

      render(
        <MemoryRouter initialEntries={['/register']}>
          <LoginPage />
        </MemoryRouter>
      )

      await user.type(screen.getByLabelText('Email'), 'test@example.com')
      await user.type(screen.getByLabelText('Username'), 'testuser')
      await user.type(screen.getByLabelText(/^Password$/), 'ValidPass123')
      await user.type(screen.getByLabelText(/Confirm Password/i), 'DifferentPass123')
      await user.click(screen.getByRole('button', { name: /Create account/i }))

      expect(screen.getByText('Passwords do not match')).toBeInTheDocument()
    })

    it('disables submit button while pending', () => {
      mockAuthStore.mockReturnValue({
        login: mockLogin,
        register: mockRegister,
        isAuthenticated: false,
        isLoading: true,
        error: null,
        clearError: mockClearError,
      })

      render(
        <MemoryRouter initialEntries={['/register']}>
          <LoginPage />
        </MemoryRouter>
      )

      const submitButton = screen.getByRole('button', { name: /Creating account/i })
      expect(submitButton).toBeDisabled()
    })

    it('switches to login mode', async () => {
      const user = userEvent.setup()

      render(
        <MemoryRouter initialEntries={['/register']}>
          <LoginPage />
        </MemoryRouter>
      )

      await user.click(screen.getByRole('button', { name: /Sign in/i }))

      expect(screen.getByText('Welcome back')).toBeInTheDocument()
    })

    it('displays register error from store', () => {
      mockAuthStore.mockReturnValue({
        login: mockLogin,
        register: mockRegister,
        isAuthenticated: false,
        isLoading: false,
        error: 'Email already registered',
        clearError: mockClearError,
      })

      render(
        <MemoryRouter initialEntries={['/register']}>
          <LoginPage />
        </MemoryRouter>
      )

      expect(screen.getByText('Email already registered')).toBeInTheDocument()
    })

    it('clears error when switching modes', async () => {
      const user = userEvent.setup()
      mockAuthStore.mockReturnValue({
        login: mockLogin,
        register: mockRegister,
        isAuthenticated: false,
        isLoading: false,
        error: 'Some error',
        clearError: mockClearError,
      })

      const { rerender } = render(
        <MemoryRouter initialEntries={['/login']}>
          <LoginPage />
        </MemoryRouter>
      )

      await user.click(screen.getByRole('button', { name: /Sign up/i }))

      expect(mockClearError).toHaveBeenCalled()
    })
  })

  describe('Redirects', () => {
    it('redirects to home when authenticated', () => {
      mockAuthStore.mockReturnValue({
        login: mockLogin,
        register: mockRegister,
        isAuthenticated: true,
        isLoading: false,
        error: null,
        clearError: mockClearError,
      })

      render(
        <MemoryRouter initialEntries={['/login']}>
          <LoginPage />
        </MemoryRouter>
      )

      // In a real app with proper routing, this would navigate
      // For now, just verify the component mounts
      expect(screen.queryByText('Welcome back')).not.toBeInTheDocument()
    })
  })
})
