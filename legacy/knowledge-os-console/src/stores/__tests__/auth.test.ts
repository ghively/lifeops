import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useAuthStore } from '../auth'

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {}

  return {
    getItem: (key: string) => store[key] || null,
    setItem: (key: string, value: string) => {
      store[key] = value.toString()
    },
    removeItem: (key: string) => {
      delete store[key]
    },
    clear: () => {
      store = {}
    },
  }
})()

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock,
})

// Mock the API
vi.mock('@/services/api', () => ({
  authApi: {
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    getMe: vi.fn(),
    refreshToken: vi.fn(),
  },
}))

import { authApi } from '@/services/api'

describe('Auth Store', () => {
  beforeEach(() => {
    // Reset store state
    localStorage.clear()
    useAuthStore.setState({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: false,
      isInitialized: false,
      error: null,
    })
    vi.clearAllMocks()
  })

  afterEach(() => {
    localStorage.clear()
  })

  describe('login', () => {
    it('stores token and user on successful login', async () => {
      const mockUser = { id: 'user-1', email: 'test@example.com', username: 'testuser', display_name: 'Test User' }
      const mockTokens = {
        access_token: 'access-123',
        refresh_token: 'refresh-123',
        user: mockUser,
      }

      vi.mocked(authApi.login).mockResolvedValue(mockTokens as any)

      await useAuthStore.getState().login('test@example.com', 'password123')

      expect(useAuthStore.getState().user).toEqual(mockUser)
      expect(useAuthStore.getState().accessToken).toBe('access-123')
      expect(useAuthStore.getState().refreshToken).toBe('refresh-123')
      expect(useAuthStore.getState().isAuthenticated).toBe(true)
      expect(localStorage.getItem('access_token')).toBe('access-123')
      expect(localStorage.getItem('refresh_token')).toBe('refresh-123')
    })

    it('sets error on failed login', async () => {
      vi.mocked(authApi.login).mockRejectedValue(new Error('Invalid credentials'))

      try {
        await useAuthStore.getState().login('test@example.com', 'wrongpass')
      } catch {
        // Expected
      }

      expect(useAuthStore.getState().error).toBe('Invalid credentials')
      expect(useAuthStore.getState().isAuthenticated).toBe(false)
    })

    it('sets isLoading during login', async () => {
      const mockTokens = {
        access_token: 'token-123',
        refresh_token: 'refresh-123',
        user: { id: 'user-1', email: 'test@example.com', username: 'testuser', display_name: '' },
      }

      vi.mocked(authApi.login).mockImplementation(
        () =>
          new Promise((resolve) => {
            setTimeout(() => resolve(mockTokens as any), 10)
          })
      )

      const loginPromise = useAuthStore.getState().login('test@example.com', 'password123')

      // Check loading state
      expect(useAuthStore.getState().isLoading).toBe(true)

      await loginPromise

      expect(useAuthStore.getState().isLoading).toBe(false)
    })

    it('clears previous error on new login', async () => {
      useAuthStore.setState({ error: 'Previous error' })

      const mockTokens = {
        access_token: 'token-123',
        refresh_token: 'refresh-123',
        user: { id: 'user-1', email: 'test@example.com', username: 'testuser', display_name: '' },
      }

      vi.mocked(authApi.login).mockResolvedValue(mockTokens as any)

      await useAuthStore.getState().login('test@example.com', 'password123')

      expect(useAuthStore.getState().error).toBe(null)
    })
  })

  describe('register', () => {
    it('stores token and user on successful register', async () => {
      const mockUser = { id: 'user-2', email: 'new@example.com', username: 'newuser', display_name: 'New User' }
      const mockTokens = {
        access_token: 'access-456',
        refresh_token: 'refresh-456',
        user: mockUser,
      }

      vi.mocked(authApi.register).mockResolvedValue(mockTokens as any)

      await useAuthStore.getState().register({
        email: 'new@example.com',
        username: 'newuser',
        password: 'SecurePass123',
        display_name: 'New User',
      })

      expect(useAuthStore.getState().user).toEqual(mockUser)
      expect(useAuthStore.getState().isAuthenticated).toBe(true)
      expect(localStorage.getItem('access_token')).toBe('access-456')
    })

    it('sets error on failed register', async () => {
      vi.mocked(authApi.register).mockRejectedValue(new Error('Email already registered'))

      try {
        await useAuthStore.getState().register({
          email: 'existing@example.com',
          username: 'existinguser',
          password: 'SecurePass123',
        })
      } catch {
        // Expected
      }

      expect(useAuthStore.getState().error).toBe('Email already registered')
      expect(useAuthStore.getState().isAuthenticated).toBe(false)
    })
  })

  describe('logout', () => {
    it('clears tokens and user on logout', async () => {
      // Setup authenticated state
      useAuthStore.setState({
        user: { id: 'user-1', email: 'test@example.com', username: 'testuser', display_name: '' },
        accessToken: 'token-123',
        refreshToken: 'refresh-123',
        isAuthenticated: true,
      })
      localStorage.setItem('access_token', 'token-123')
      localStorage.setItem('refresh_token', 'refresh-123')

      vi.mocked(authApi.logout).mockResolvedValue({} as any)

      await useAuthStore.getState().logout()

      expect(useAuthStore.getState().user).toBeNull()
      expect(useAuthStore.getState().accessToken).toBeNull()
      expect(useAuthStore.getState().refreshToken).toBeNull()
      expect(useAuthStore.getState().isAuthenticated).toBe(false)
      expect(localStorage.getItem('access_token')).toBeNull()
      expect(localStorage.getItem('refresh_token')).toBeNull()
    })

    it('handles logout API failure gracefully', async () => {
      useAuthStore.setState({
        user: { id: 'user-1', email: 'test@example.com', username: 'testuser', display_name: '' },
        accessToken: 'token-123',
        refreshToken: 'refresh-123',
        isAuthenticated: true,
      })

      vi.mocked(authApi.logout).mockRejectedValue(new Error('API error'))

      // Should not throw
      await useAuthStore.getState().logout()

      // Should still clear local state
      expect(useAuthStore.getState().isAuthenticated).toBe(false)
    })
  })

  describe('refreshAccessToken', () => {
    it('updates access token on successful refresh', async () => {
      localStorage.setItem('refresh_token', 'refresh-123')

      const newTokens = {
        access_token: 'new-access-456',
        refresh_token: 'new-refresh-456',
        user: { id: 'user-1', email: 'test@example.com', username: 'testuser', display_name: '' },
      }

      vi.mocked(authApi.refreshToken).mockResolvedValue(newTokens as any)

      await useAuthStore.getState().refreshAccessToken()

      expect(localStorage.getItem('access_token')).toBe('new-access-456')
      expect(localStorage.getItem('refresh_token')).toBe('new-refresh-456')
      expect(useAuthStore.getState().isAuthenticated).toBe(true)
    })

    it('clears auth on failed refresh', async () => {
      localStorage.setItem('refresh_token', 'refresh-123')
      useAuthStore.setState({ isAuthenticated: true })

      vi.mocked(authApi.refreshToken).mockRejectedValue(new Error('Token expired'))

      try {
        await useAuthStore.getState().refreshAccessToken()
      } catch {
        // Expected
      }

      expect(useAuthStore.getState().isAuthenticated).toBe(false)
      expect(localStorage.getItem('access_token')).toBeNull()
      expect(localStorage.getItem('refresh_token')).toBeNull()
    })

    it('throws error if no refresh token available', async () => {
      localStorage.clear()

      await expect(useAuthStore.getState().refreshAccessToken()).rejects.toThrow(
        'No refresh token available'
      )
    })
  })

  describe('clearError', () => {
    it('clears error message', () => {
      useAuthStore.setState({ error: 'Some error' })

      useAuthStore.getState().clearError()

      expect(useAuthStore.getState().error).toBeNull()
    })
  })

  describe('initialize', () => {
    it('initializes with stored tokens', async () => {
      const mockUser = { id: 'user-1', email: 'test@example.com', username: 'testuser', display_name: '' }
      localStorage.setItem('refresh_token', 'refresh-123')
      localStorage.setItem('access_token', 'access-123')

      vi.mocked(authApi.getMe).mockResolvedValue(mockUser as any)

      await useAuthStore.getState().initialize()

      expect(useAuthStore.getState().isInitialized).toBe(true)
      expect(useAuthStore.getState().user).toEqual(mockUser)
    })

    it('marks as initialized when no tokens present', async () => {
      localStorage.clear()

      await useAuthStore.getState().initialize()

      expect(useAuthStore.getState().isInitialized).toBe(true)
      expect(useAuthStore.getState().isAuthenticated).toBe(false)
    })

    it('handles getMe failure gracefully', async () => {
      localStorage.setItem('refresh_token', 'refresh-123')
      localStorage.setItem('access_token', 'access-123')

      vi.mocked(authApi.getMe).mockRejectedValue(new Error('Unauthorized'))

      await useAuthStore.getState().initialize()

      expect(useAuthStore.getState().isInitialized).toBe(true)
    })
  })

  describe('refreshUser', () => {
    it('updates user profile', async () => {
      const mockUser = { id: 'user-1', email: 'test@example.com', username: 'testuser', display_name: 'Updated Name' }

      vi.mocked(authApi.getMe).mockResolvedValue(mockUser as any)

      await useAuthStore.getState().refreshUser()

      expect(useAuthStore.getState().user).toEqual(mockUser)
      expect(useAuthStore.getState().isInitialized).toBe(true)
    })

    it('handles getMe failure gracefully', async () => {
      vi.mocked(authApi.getMe).mockRejectedValue(new Error('Unauthorized'))

      await useAuthStore.getState().refreshUser()

      expect(useAuthStore.getState().isInitialized).toBe(true)
    })
  })
})
