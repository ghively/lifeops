import { X } from 'lucide-react'
import { useThemeStore, type ThemeName, type AccentName, type DensityName } from '@/stores/theme'

const THEMES: { val: ThemeName; label: string }[] = [
  { val: 'paper', label: 'Paper' },
  { val: 'midnight', label: 'Midnight' },
  { val: 'linen', label: 'Linen' },
]

const ACCENTS: { val: AccentName; color: string }[] = [
  { val: 'terracotta', color: 'oklch(0.63 0.13 40)' },
  { val: 'olive', color: 'oklch(0.63 0.13 120)' },
  { val: 'indigo', color: 'oklch(0.55 0.13 265)' },
  { val: 'plum', color: 'oklch(0.55 0.13 330)' },
]

const DENSITIES: { val: DensityName; label: string }[] = [
  { val: 'cozy', label: 'Cozy' },
  { val: 'compact', label: 'Compact' },
]

export function TweaksPanel() {
  const {
    theme,
    accent,
    density,
    showGrain,
    serifTitles,
    tweaksOpen,
    setTheme,
    setAccent,
    setDensity,
    setShowGrain,
    setSerifTitles,
    setTweaksOpen,
  } = useThemeStore()

  if (!tweaksOpen) return null

  return (
    <div className="kos-tweaks" role="dialog" aria-label="Tweaks">
      <h4>
        <span>
          Tweaks <em>— preview</em>
        </span>
        <button
          type="button"
          aria-label="Close tweaks"
          onClick={() => setTweaksOpen(false)}
          className="kos-icon-btn"
          style={{ color: 'var(--ink-mute)' }}
        >
          <X size={14} />
        </button>
      </h4>

      <div className="kos-tweak-row">
        <span>Theme</span>
        <div className="kos-pill-row" role="radiogroup" aria-label="Theme">
          {THEMES.map((t) => (
            <button
              key={t.val}
              type="button"
              className={t.val === theme ? 'on' : ''}
              onClick={() => setTheme(t.val)}
              role="radio"
              aria-checked={t.val === theme}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="kos-tweak-row">
        <span>Accent</span>
        <div className="kos-swatch-row" role="radiogroup" aria-label="Accent">
          {ACCENTS.map((a) => (
            <button
              key={a.val}
              type="button"
              className={`kos-sw ${a.val === accent ? 'on' : ''}`}
              style={{ background: a.color }}
              onClick={() => setAccent(a.val)}
              role="radio"
              aria-checked={a.val === accent}
              aria-label={`Accent ${a.val}`}
            />
          ))}
        </div>
      </div>

      <div className="kos-tweak-row">
        <span>Density</span>
        <div className="kos-pill-row" role="radiogroup" aria-label="Density">
          {DENSITIES.map((d) => (
            <button
              key={d.val}
              type="button"
              className={d.val === density ? 'on' : ''}
              onClick={() => setDensity(d.val)}
              role="radio"
              aria-checked={d.val === density}
            >
              {d.label}
            </button>
          ))}
        </div>
      </div>

      <div className="kos-tweak-row">
        <span>Paper grain</span>
        <button
          type="button"
          className={`kos-toggle ${showGrain ? 'on' : ''}`}
          onClick={() => setShowGrain(!showGrain)}
          role="switch"
          aria-checked={showGrain}
          aria-label="Paper grain"
        />
      </div>

      <div className="kos-tweak-row">
        <span>Serif titles</span>
        <button
          type="button"
          className={`kos-toggle ${serifTitles ? 'on' : ''}`}
          onClick={() => setSerifTitles(!serifTitles)}
          role="switch"
          aria-checked={serifTitles}
          aria-label="Serif titles"
        />
      </div>
    </div>
  )
}
