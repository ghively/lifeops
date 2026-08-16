import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { authApi, type User, type RegisterData } from '@/services/api'

interface AuthState {
  user: User | null
  accessToken: string | null
  refreshToken: string | null
  isAuthenticated: boolean
  isLoading: boolean
  isInitialized: boolean
  error: string | null

  // Actions
  login: (email: string, password: string) => Promise<void>
  register: (data: RegisterData) => Promise<void>
  logout: () => Promise<void>
  refreshUser: () => Promise<void>
  refreshAccessToken: () => Promise<void>
  clearError: () => void
  initialize: () => Promise<void>
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: false,
      isInitialized: false,
      error: null,

      login: async (email: string, password: string) => {
        set({ isLoading: true, error: null })
        try {
          const response = await authApi.login(email, password)
          // Store tokens: refresh in localStorage (survives refresh), access in memory+localStorage
          localStorage.setItem('refresh_token', response.refresh_token)
          localStorage.setItem('access_token', response.access_token)
          set({
            user: response.user,
            accessToken: response.access_token,
            refreshToken: response.refresh_token,
            isAuthenticated: true,
            isLoading: false,
          })
        } catch (error: unknown) {
          const message = error instanceof Error ? error.message : 'Login failed'
          set({ error: message, isLoading: false })
          throw error
        }
      },

      register: async (data: RegisterData) => {
        set({ isLoading: true, error: null })
        try {
          const response = await authApi.register(data)
          localStorage.setItem('refresh_token', response.refresh_token)
          localStorage.setItem('access_token', response.access_token)
          set({
            user: response.user,
            accessToken: response.access_token,
            refreshToken: response.refresh_token,
            isAuthenticated: true,
            isLoading: false,
          })
        } catch (error: unknown) {
          const message = error instanceof Error ? error.message : 'Registration failed'
          set({ error: message, isLoading: false })
          throw error
        }
      },

      logout: async () => {
        const { refreshToken } = get()
        try {
          if (refreshToken) {
            await authApi.logout(refreshToken)
          }
        } catch (error) {
          console.error('Logout error:', error)
        } finally {
          localStorage.removeItem('refresh_token')
          localStorage.removeItem('access_token')
          set({
            user: null,
            accessToken: null,
            refreshToken: null,
            isAuthenticated: false,
          })
          // Clear persisted Zustand state so rehydration doesn't restore stale auth
          useAuthStore.persist.clearStorage()
        }
      },

      refreshUser: async () => {
        // Let the axios interceptor handle token refresh on 401.
        // This just fetches the current user profile.
        try {
          const user = await authApi.getMe()
          set({ user, isInitialized: true })
        } catch {
          // If getMe fails (e.g. refresh also failed), interceptor handles redirect
          set({ isInitialized: true })
        }
      },

      refreshAccessToken: async () => {
        const refreshToken = localStorage.getItem('refresh_token')
        if (!refreshToken) {
          throw new Error('No refresh token available')
        }

        try {
          const response = await authApi.refreshToken(refreshToken)
          localStorage.setItem('access_token', response.access_token)
          if (response.refresh_token) {
            localStorage.setItem('refresh_token', response.refresh_token)
          }
          set({
            user: response.user,
            accessToken: response.access_token,
            refreshToken: response.refresh_token,
            isAuthenticated: true,
          })
        } catch (error) {
          localStorage.removeItem('refresh_token')
          localStorage.removeItem('access_token')
          set({
            user: null,
            accessToken: null,
            refreshToken: null,
            isAuthenticated: false,
          })
          throw error
        }
      },

      clearError: () => set({ error: null }),

      initialize: async () => {
        const refreshToken = localStorage.getItem('refresh_token')
        const accessToken = localStorage.getItem('access_token')

        if (!refreshToken && !accessToken) {
          set({ isInitialized: true, isAuthenticated: false })
          return
        }

        // Restore tokens from localStorage into Zustand state
        if (accessToken) {
          set({ accessToken, isAuthenticated: true })
        }
        if (refreshToken) {
          set({ refreshToken })
        }

        // Verify the session is still valid by fetching user profile
        // The axios interceptor will handle token refresh if needed
        try {
          const user = await authApi.getMe()
          set({ user, isAuthenticated: true, isInitialized: true })
        } catch {
          // Session invalid — interceptor already tried refresh and failed
          set({ isAuthenticated: false, isInitialized: true })
          localStorage.removeItem('refresh_token')
          localStorage.removeItem('access_token')
          if (typeof window !== 'undefined') {
            window.location.href = '/login'
          }
        }
      },
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
)
