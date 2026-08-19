import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type ThemeName = 'paper' | 'midnight' | 'linen'
export type AccentName = 'terracotta' | 'olive' | 'indigo' | 'plum'
export type DensityName = 'cozy' | 'compact'

export interface ThemeState {
  theme: ThemeName
  accent: AccentName
  density: DensityName
  showGrain: boolean
  serifTitles: boolean

  setTheme: (theme: ThemeName) => void
  setAccent: (accent: AccentName) => void
  setDensity: (density: DensityName) => void
  setShowGrain: (v: boolean) => void
  setSerifTitles: (v: boolean) => void
}

// One-time migration: settings persisted under the pre-fork key move to the
// new one, then the old key is removed.
if (typeof localStorage !== 'undefined') {
  const legacy = localStorage.getItem('knowledge-os:theme')
  if (legacy !== null && localStorage.getItem('lifeops:theme') === null) {
    localStorage.setItem('lifeops:theme', legacy)
  }
  if (legacy !== null) {
    localStorage.removeItem('knowledge-os:theme')
  }
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      theme: 'paper',
      accent: 'terracotta',
      density: 'cozy',
      showGrain: true,
      serifTitles: true,

      setTheme: (theme) => set({ theme }),
      setAccent: (accent) => set({ accent }),
      setDensity: (density) => set({ density }),
      setShowGrain: (showGrain) => set({ showGrain }),
      setSerifTitles: (serifTitles) => set({ serifTitles }),
    }),
    {
      // Renamed from the pre-fork 'knowledge-os:theme'; the one-time
      // migration below carries an existing choice across so nobody's
      // theme resets.
      name: 'lifeops:theme',
      partialize: (s) => ({
        theme: s.theme,
        accent: s.accent,
        density: s.density,
        showGrain: s.showGrain,
        serifTitles: s.serifTitles,
      }),
    },
  ),
)
