/**
 * Notification button must reliably fire its onClick handler and surface
 * a visible status pill so the user knows the click was handled
 * (regression for issue #154).
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { MainLayout } from '../MainLayout'

vi.mock('@/hooks/useAgentNotifications', () => ({
  useAgentNotifications: () => undefined,
}))

vi.mock('@/hooks/useInstallPrompt', () => ({
  useInstallPrompt: () => ({ canInstall: false, install: vi.fn() }),
}))

vi.mock('@/hooks/useMediaQuery', () => ({
  useMediaQuery: () => false,
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ isAuthenticated: true }),
}))

vi.mock('@/stores/theme', () => ({
  useThemeStore: () => ({ toggleTweaks: vi.fn() }),
}))

vi.mock('../Sidebar', () => ({
  Sidebar: () => <div data-testid="stub-sidebar" />,
}))

function renderLayout() {
  return render(
    <MemoryRouter>
      <MainLayout>
        <div>child</div>
      </MainLayout>
    </MemoryRouter>,
  )
}

function setNotificationApi(
  permission: NotificationPermission | 'default',
  requestPermission?: () => Promise<NotificationPermission>,
) {
  const ctor = function () {} as unknown as typeof Notification
  Object.assign(ctor, {
    permission,
    requestPermission:
      requestPermission ?? vi.fn().mockResolvedValue(permission),
  })
  ;(globalThis as unknown as { Notification: typeof Notification }).Notification = ctor
}

function clearNotificationApi() {
  delete (globalThis as unknown as { Notification?: unknown }).Notification
}

describe('MainLayout notifications button (issue #154)', () => {
  afterEach(() => {
    clearNotificationApi()
  })

  it('requests permission and shows a status pill when permission is default', async () => {
    const requestPermission = vi.fn().mockResolvedValue('granted' as NotificationPermission)
    setNotificationApi('default', requestPermission)

    renderLayout()
    fireEvent.click(screen.getByTestId('header-notifications-btn'))

    await waitFor(() => expect(requestPermission).toHaveBeenCalledTimes(1))
    expect(screen.getByTestId('notif-status').textContent).toMatch(/enabled/i)
  })

  it('shows "already on" feedback when permission is already granted', async () => {
    setNotificationApi('granted')

    renderLayout()
    fireEvent.click(screen.getByTestId('header-notifications-btn'))

    expect(await screen.findByTestId('notif-status')).toHaveTextContent(/already on/i)
  })

  it('shows a denied pill when the browser blocks the request', async () => {
    setNotificationApi('denied')

    renderLayout()
    fireEvent.click(screen.getByTestId('header-notifications-btn'))

    expect(await screen.findByTestId('notif-status')).toHaveTextContent(/blocked/i)
  })

  it('reports unsupported when the Notification API is missing', async () => {
    clearNotificationApi()

    renderLayout()
    fireEvent.click(screen.getByTestId('header-notifications-btn'))

    expect(await screen.findByTestId('notif-status')).toHaveTextContent(/not supported/i)
  })
})
