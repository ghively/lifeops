import { useEffect } from 'react'
import { useThemeStore } from '@/stores/theme'

const THEME_CLASSES = ['theme-paper', 'theme-midnight', 'theme-linen']
const ACCENT_CLASSES = ['accent-terracotta', 'accent-olive', 'accent-indigo', 'accent-plum']
const DENSITY_CLASSES = ['density-cozy', 'density-compact']

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const { theme, accent, density, showGrain, serifTitles } = useThemeStore()

  useEffect(() => {
    const root = document.documentElement
    const body = document.body

    THEME_CLASSES.forEach((c) => root.classList.remove(c))
    ACCENT_CLASSES.forEach((c) => root.classList.remove(c))
    DENSITY_CLASSES.forEach((c) => root.classList.remove(c))

    root.classList.add(`theme-${theme}`)
    root.classList.add(`accent-${accent}`)
    root.classList.add(`density-${density}`)

    body.classList.toggle('no-grain', !showGrain)
    body.classList.toggle('no-serif-titles', !serifTitles)
  }, [theme, accent, density, showGrain, serifTitles])

  return <>{children}</>
}
