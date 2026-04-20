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
  tweaksOpen: boolean

  setTheme: (theme: ThemeName) => void
  setAccent: (accent: AccentName) => void
  setDensity: (density: DensityName) => void
  setShowGrain: (v: boolean) => void
  setSerifTitles: (v: boolean) => void
  toggleTweaks: () => void
  setTweaksOpen: (v: boolean) => void
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      theme: 'paper',
      accent: 'terracotta',
      density: 'cozy',
      showGrain: true,
      serifTitles: true,
      tweaksOpen: false,

      setTheme: (theme) => set({ theme }),
      setAccent: (accent) => set({ accent }),
      setDensity: (density) => set({ density }),
      setShowGrain: (showGrain) => set({ showGrain }),
      setSerifTitles: (serifTitles) => set({ serifTitles }),
      toggleTweaks: () => set((s) => ({ tweaksOpen: !s.tweaksOpen })),
      setTweaksOpen: (tweaksOpen) => set({ tweaksOpen }),
    }),
    {
      name: 'knowledge-os:theme',
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
