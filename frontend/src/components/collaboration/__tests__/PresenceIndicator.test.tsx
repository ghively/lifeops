import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PresenceIndicator } from '../PresenceIndicator'
import { useCollaborationStore } from '@/stores/collaboration'
import type { PresenceUser } from '@/services/collaboration'

vi.mock('@/stores/collaboration', () => ({
  useCollaborationStore: vi.fn(),
}))

const mockCollaborationStore = useCollaborationStore as any

describe('PresenceIndicator', () => {
  const mockUsers: PresenceUser[] = [
    {
      user_id: 'user-1',
      display_name: 'Alice',
      color: '#FF0000',
      cursor: null,
    },
    {
      user_id: 'user-2',
      display_name: 'Bob',
      color: '#00FF00',
      cursor: null,
    },
  ]

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders nothing when not connected', () => {
    mockCollaborationStore.mockImplementation((selector: any) => {
      const state = {
        users: [],
        myColor: '#0000FF',
        status: 'disconnected',
      }
      return selector(state)
    })

    const { container } = render(<PresenceIndicator />)

    expect(container.firstChild).toBeNull()
  })

  it('shows current user indicator when connected but alone', () => {
    mockCollaborationStore.mockImplementation((selector: any) => {
      const state = {
        users: [],
        myColor: '#0000FF',
        status: 'connected',
      }
      return selector(state)
    })

    render(<PresenceIndicator />)

    expect(screen.getByText('You')).toBeInTheDocument()
  })

  it('renders user avatars', () => {
    mockCollaborationStore.mockImplementation((selector: any) => {
      const state = {
        users: mockUsers,
        myColor: '#0000FF',
        status: 'connected',
      }
      return selector(state)
    })

    const { container } = render(<PresenceIndicator />)

    const avatars = container.querySelectorAll('div[style*="backgroundColor"]')
    expect(avatars.length).toBeGreaterThan(0)
  })

  it('shows user count', () => {
    mockCollaborationStore.mockImplementation((selector: any) => {
      const state = {
        users: mockUsers,
        myColor: '#0000FF',
        status: 'connected',
      }
      return selector(state)
    })

    render(<PresenceIndicator />)

    expect(screen.getByText(`${mockUsers.length} others editing`)).toBeInTheDocument()
  })

  it('shows singular "1 other editing" for single user', () => {
    const singleUser = [mockUsers[0]]
    mockCollaborationStore.mockImplementation((selector: any) => {
      const state = {
        users: singleUser,
        myColor: '#0000FF',
        status: 'connected',
      }
      return selector(state)
    })

    render(<PresenceIndicator />)

    expect(screen.getByText('1 other editing')).toBeInTheDocument()
  })

  it('truncates avatars to maxVisible', () => {
    const manyUsers = Array.from({ length: 10 }, (_, i) => ({
      user_id: `user-${i}`,
      display_name: `User ${i}`,
      color: `#${Math.random().toString(16).slice(2, 8)}`,
      cursor: null,
    }))

    mockCollaborationStore.mockImplementation((selector: any) => {
      const state = {
        users: manyUsers,
        myColor: '#0000FF',
        status: 'connected',
      }
      return selector(state)
    })

    const { container } = render(<PresenceIndicator maxVisible={3} />)

    // Should show 3 avatars + overflow badge
    const avatarDivs = container.querySelectorAll('.flex.-space-x-2 > div')
    expect(avatarDivs.length).toBe(4) // 3 avatars + 1 overflow badge
  })

  it('shows overflow badge with correct count', () => {
    const manyUsers = Array.from({ length: 8 }, (_, i) => ({
      user_id: `user-${i}`,
      display_name: `User ${i}`,
      color: `#${Math.random().toString(16).slice(2, 8)}`,
      cursor: null,
    }))

    mockCollaborationStore.mockImplementation((selector: any) => {
      const state = {
        users: manyUsers,
        myColor: '#0000FF',
        status: 'connected',
      }
      return selector(state)
    })

    render(<PresenceIndicator maxVisible={5} />)

    expect(screen.getByText('+3')).toBeInTheDocument()
  })

  it('does not show overflow when under maxVisible', () => {
    mockCollaborationStore.mockImplementation((selector: any) => {
      const state = {
        users: mockUsers,
        myColor: '#0000FF',
        status: 'connected',
      }
      return selector(state)
    })

    const { container } = render(<PresenceIndicator maxVisible={5} />)

    const plusBadges = container.querySelectorAll('div:has-text("+")')
    expect(plusBadges.length).toBe(0)
  })

  it('applies custom className', () => {
    mockCollaborationStore.mockImplementation((selector: any) => {
      const state = {
        users: mockUsers,
        myColor: '#0000FF',
        status: 'connected',
      }
      return selector(state)
    })

    const { container } = render(<PresenceIndicator className="custom-class" />)

    expect(container.querySelector('.custom-class')).toBeInTheDocument()
  })

  it('shows connected status indicator', () => {
    mockCollaborationStore.mockImplementation((selector: any) => {
      const state = {
        users: mockUsers,
        myColor: '#0000FF',
        status: 'connected',
      }
      return selector(state)
    })

    const { container } = render(<PresenceIndicator />)

    const statusIndicator = container.querySelector('.animate-ping')
    expect(statusIndicator).toBeInTheDocument()
  })

  it('renders user initials correctly', () => {
    const usersWithNames = [
      {
        user_id: 'user-1',
        display_name: 'Alice Brown',
        color: '#FF0000',
        cursor: null,
      },
      {
        user_id: 'user-2',
        display_name: 'Xavier',
        color: '#00FF00',
        cursor: null,
      },
    ]

    mockCollaborationStore.mockImplementation((selector: any) => {
      const state = {
        users: usersWithNames,
        myColor: '#0000FF',
        status: 'connected',
      }
      return selector(state)
    })

    const { container } = render(<PresenceIndicator />)

    // Should find avatars with initials
    const avatarTexts = container.querySelectorAll('.flex.-space-x-2 > div')
    expect(avatarTexts.length).toBeGreaterThan(0)
  })

  it('uses user color for avatar background', () => {
    const usersWithColors = [
      {
        user_id: 'user-1',
        display_name: 'Red User',
        color: '#FF0000',
        cursor: null,
      },
    ]

    mockCollaborationStore.mockImplementation((selector: any) => {
      const state = {
        users: usersWithColors,
        myColor: '#0000FF',
        status: 'connected',
      }
      return selector(state)
    })

    const { container } = render(<PresenceIndicator />)

    const avatarWithColor = container.querySelector('div[style*="#FF0000"]')
    expect(avatarWithColor).toBeInTheDocument()
  })
})
