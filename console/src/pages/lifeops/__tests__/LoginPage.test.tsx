/**
 * Login screen behaviour: a correct password stores the token and unlocks the
 * app; a wrong one shows the server's reason and keeps the session closed.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getToken, useAuthStore } from '@/lib/auth'
import { authApi, LifeOpsError } from '@/services/lifeops'
import { LoginPage } from '../LoginPage'

vi.mock('@/services/lifeops', async () => {
  const actual = await vi.importActual<typeof import('@/services/lifeops')>(
    '@/services/lifeops',
  )
  return {
    ...actual,
    authApi: {
      login: vi.fn(),
      me: vi.fn(),
    },
  }
})

const mockedAuth = vi.mocked(authApi)

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  useAuthStore.setState({ status: 'unauthenticated' })
})

describe('LoginPage', () => {
  it('stores the token and authenticates on success', async () => {
    mockedAuth.login.mockResolvedValue({ token: 'tok_new' })
    render(<LoginPage />)

    await userEvent.type(screen.getByLabelText('Password'), 'correct horse')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(getToken()).toBe('tok_new'))
    expect(mockedAuth.login).toHaveBeenCalledWith('correct horse')
    expect(useAuthStore.getState().status).toBe('authenticated')
  })

  it('shows the server reason on a wrong password and stores nothing', async () => {
    mockedAuth.login.mockRejectedValue(
      new LifeOpsError('invalid_credentials', 'wrong password', 401),
    )
    render(<LoginPage />)

    await userEvent.type(screen.getByLabelText('Password'), 'nope')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('wrong password')
    expect(getToken()).toBeNull()
    expect(useAuthStore.getState().status).toBe('unauthenticated')
  })

  it('keeps the button disabled until a password is entered', () => {
    render(<LoginPage />)
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeDisabled()
  })
})
