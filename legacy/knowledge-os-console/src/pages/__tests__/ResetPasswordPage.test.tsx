import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BrowserRouter } from 'react-router-dom'
import { ResetPasswordPage } from '../ResetPasswordPage'
import { authApi } from '@/services/api'

vi.mock('@/services/api', () => ({
  authApi: {
    requestPasswordReset: vi.fn(),
    confirmPasswordReset: vi.fn(),
  },
}))

const mockAuthApi = authApi as any

describe('ResetPasswordPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const renderPage = () =>
    render(
      <BrowserRouter>
        <ResetPasswordPage />
      </BrowserRouter>
    )

  // ── Request step ────────────────────────────────────────────────────────────

  it('renders the reset-password heading', () => {
    renderPage()
    expect(
      screen.getByRole('heading', { name: /reset your password/i })
    ).toBeInTheDocument()
  })

  it('renders the email input on the request step', () => {
    renderPage()
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument()
  })

  it('renders the Send reset link submit button', () => {
    renderPage()
    expect(
      screen.getByRole('button', { name: /send reset link/i })
    ).toBeInTheDocument()
  })

  it('renders the Back to login link', () => {
    renderPage()
    expect(screen.getByRole('link', { name: /back to login/i })).toBeInTheDocument()
  })

  it('advances to the confirm step after a successful reset request', async () => {
    const user = userEvent.setup()
    mockAuthApi.requestPasswordReset.mockResolvedValue({ message: 'Email sent' })

    renderPage()

    const emailInput = screen.getByLabelText(/email/i)
    await user.type(emailInput, 'user@example.com')

    const submitButton = screen.getByRole('button', { name: /send reset link/i })
    await user.click(submitButton)

    await waitFor(() => {
      expect(
        screen.getByText(/enter the reset token and your new password/i)
      ).toBeInTheDocument()
    })
    expect(mockAuthApi.requestPasswordReset).toHaveBeenCalledWith('user@example.com')
  })

  it('shows an error message when requestPasswordReset rejects', async () => {
    const user = userEvent.setup()
    mockAuthApi.requestPasswordReset.mockRejectedValue(new Error('User not found'))

    renderPage()

    const emailInput = screen.getByLabelText(/email/i)
    await user.type(emailInput, 'unknown@example.com')

    const submitButton = screen.getByRole('button', { name: /send reset link/i })
    await user.click(submitButton)

    await waitFor(() => {
      expect(screen.getByText(/user not found/i)).toBeInTheDocument()
    })
  })

  // ── Confirm step ────────────────────────────────────────────────────────────

  it('shows token and new-password fields on the confirm step', async () => {
    const user = userEvent.setup()
    mockAuthApi.requestPasswordReset.mockResolvedValue({ message: 'Email sent' })

    renderPage()

    await user.type(screen.getByLabelText(/email/i), 'user@example.com')
    await user.click(screen.getByRole('button', { name: /send reset link/i }))

    await waitFor(() => {
      expect(screen.getByLabelText(/reset token/i)).toBeInTheDocument()
    })
    // Use the input ids to avoid ambiguity with "Confirm New Password"
    expect(document.getElementById('new-password')).toBeInTheDocument()
    expect(document.getElementById('confirm-password')).toBeInTheDocument()
  })

  it('shows validation error when passwords do not match on confirm step', async () => {
    const user = userEvent.setup()
    mockAuthApi.requestPasswordReset.mockResolvedValue({ message: 'Email sent' })

    renderPage()

    // Navigate to confirm step
    await user.type(screen.getByLabelText(/email/i), 'user@example.com')
    await user.click(screen.getByRole('button', { name: /send reset link/i }))
    await waitFor(() => {
      expect(screen.getByLabelText(/reset token/i)).toBeInTheDocument()
    })

    // Fill in mismatched passwords using element ids to avoid label ambiguity
    await user.type(screen.getByLabelText(/reset token/i), 'some-token')
    await user.type(document.getElementById('new-password')!, 'password123')
    await user.type(document.getElementById('confirm-password')!, 'different456')

    await user.click(screen.getByRole('button', { name: /reset password/i }))

    await waitFor(() => {
      expect(screen.getByText(/passwords do not match/i)).toBeInTheDocument()
    })
  })

  it('shows validation error when new password is too short', async () => {
    const user = userEvent.setup()
    mockAuthApi.requestPasswordReset.mockResolvedValue({ message: 'Email sent' })

    renderPage()

    // Navigate to confirm step
    await user.type(screen.getByLabelText(/email/i), 'user@example.com')
    await user.click(screen.getByRole('button', { name: /send reset link/i }))
    await waitFor(() => {
      expect(screen.getByLabelText(/reset token/i)).toBeInTheDocument()
    })

    await user.type(screen.getByLabelText(/reset token/i), 'some-token')
    await user.type(document.getElementById('new-password')!, 'short')
    await user.type(document.getElementById('confirm-password')!, 'short')

    await user.click(screen.getByRole('button', { name: /reset password/i }))

    await waitFor(() => {
      expect(screen.getByText(/at least 8 characters/i)).toBeInTheDocument()
    })
  })

  it('shows success message after a successful password reset', async () => {
    const user = userEvent.setup()
    mockAuthApi.requestPasswordReset.mockResolvedValue({ message: 'Email sent' })
    mockAuthApi.confirmPasswordReset.mockResolvedValue({ message: 'Password reset' })

    renderPage()

    // Step 1: request
    await user.type(screen.getByLabelText(/email/i), 'user@example.com')
    await user.click(screen.getByRole('button', { name: /send reset link/i }))
    await waitFor(() => {
      expect(screen.getByLabelText(/reset token/i)).toBeInTheDocument()
    })

    // Step 2: confirm — use element ids to avoid label ambiguity
    await user.type(screen.getByLabelText(/reset token/i), 'valid-token-123')
    await user.type(document.getElementById('new-password')!, 'newpassword1')
    await user.type(document.getElementById('confirm-password')!, 'newpassword1')
    await user.click(screen.getByRole('button', { name: /reset password/i }))

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: /password reset successful/i })
      ).toBeInTheDocument()
    })
    expect(mockAuthApi.confirmPasswordReset).toHaveBeenCalledWith(
      'valid-token-123',
      'newpassword1'
    )
  })

  it('shows an error when confirmPasswordReset rejects', async () => {
    const user = userEvent.setup()
    mockAuthApi.requestPasswordReset.mockResolvedValue({ message: 'Email sent' })
    mockAuthApi.confirmPasswordReset.mockRejectedValue(new Error('Invalid token'))

    renderPage()

    // Navigate to confirm step
    await user.type(screen.getByLabelText(/email/i), 'user@example.com')
    await user.click(screen.getByRole('button', { name: /send reset link/i }))
    await waitFor(() => {
      expect(screen.getByLabelText(/reset token/i)).toBeInTheDocument()
    })

    await user.type(screen.getByLabelText(/reset token/i), 'bad-token')
    await user.type(document.getElementById('new-password')!, 'validpassword')
    await user.type(document.getElementById('confirm-password')!, 'validpassword')
    await user.click(screen.getByRole('button', { name: /reset password/i }))

    await waitFor(() => {
      expect(screen.getByText(/invalid token/i)).toBeInTheDocument()
    })
  })
})
