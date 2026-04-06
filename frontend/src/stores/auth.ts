import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { authApi, type User, type RegisterData } from '@/services/api'

interface AuthState {
  user: User | null
  accessToken: string | null
  refreshToken: string | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null

  // Actions
  login: (email: string, password: string) => Promise<void>
  register: (data: RegisterData) => Promise<void>
  logout: () => Promise<void>
  refreshUser: () => Promise<void>
  refreshAccessToken: () => Promise<void>
  clearError: () => void
  initialize: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,

      login: async (email: string, password: string) => {
        set({ isLoading: true, error: null })
        try {
          const response = await authApi.login(email, password)
          // SECURITY (H51): Access token kept in memory only (not localStorage) to mitigate XSS token theft.
          // Refresh token is persisted in localStorage as a stopgap; the recommended migration path
          // is to move refresh tokens to httpOnly cookies set by the backend, eliminating client-side
          // access entirely. See: https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html
          localStorage.setItem('refresh_token', response.refresh_token)
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
          // SECURITY (H51): See login handler comment re: localStorage token storage.
          localStorage.setItem('refresh_token', response.refresh_token)
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
          set({
            user: null,
            accessToken: null,
            refreshToken: null,
            isAuthenticated: false,
          })
        }
      },

      refreshUser: async () => {
        const { isAuthenticated } = get()
        if (!isAuthenticated) return

        set({ isLoading: true, error: null })
        try {
          const user = await authApi.getMe()
          set({ user, isLoading: false })
        } catch (error) {
          // Token might be expired, try to refresh
          const { refreshToken } = get()
          if (refreshToken) {
            try {
              await get().refreshAccessToken()
            } catch {
              // H72: Refresh failed, clear auth state and redirect to login
              localStorage.removeItem('refresh_token')
              set({
                user: null,
                accessToken: null,
                refreshToken: null,
                isAuthenticated: false,
                isLoading: false,
              })
              if (typeof window !== 'undefined') {
                window.location.href = '/login'
              }
            }
          } else {
            set({ isLoading: false })
          }
        }
      },

      refreshAccessToken: async () => {
        const { refreshToken } = get()
        if (!refreshToken) {
          throw new Error('No refresh token available')
        }

        try {
          const response = await authApi.refreshToken(refreshToken)
          // SECURITY (H51): Access token kept in memory only.
          if (response.refresh_token) {
          }
          set({
            user: response.user,
            accessToken: response.access_token,
            refreshToken: response.refresh_token,
            isAuthenticated: true,
          })
        } catch (error) {
          localStorage.removeItem('refresh_token')
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

      initialize: () => {
        const refreshToken = localStorage.getItem('refresh_token')
        if (refreshToken) {
          set({
            refreshToken,
            isAuthenticated: true,
          })
          // Fetch user data
          get().refreshUser()
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

// Initialize auth on app load
if (typeof window !== 'undefined') {
  useAuthStore.getState().initialize()
}
