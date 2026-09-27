'use client'

/**
 * Settings (Q33): reached from the "⋯" at the end of the app bar, not a main destination.
 *
 * The first setting is the theme (Q31): System follows the iPad's own appearance, Light and
 * Dark force one. It is a per-device choice, kept on this device (`lib/theme`), because the
 * kitchen iPad is the device that matters and a phone should keep its own.
 */

import { useEffect, useState } from 'react'
import { readTheme, saveTheme, THEME_CHOICES, type ThemeChoice } from '@/lib/theme'

const LABELS: Record<ThemeChoice, { name: string; hint: string }> = {
  system: { name: 'System', hint: 'Follow this device' },
  light: { name: 'Light', hint: 'Always light' },
  dark: { name: 'Dark', hint: 'Always dark' },
}

export default function SettingsPage() {
  const [theme, setTheme] = useState<ThemeChoice>('system')

  // Read after mounting: the server cannot know what this device stored
  useEffect(() => {
    setTheme(readTheme())
  }, [])

  const choose = (choice: ThemeChoice) => {
    setTheme(choice)
    saveTheme(choice)
  }

  return (
    <main className="mx-auto w-full max-w-xl px-4 py-6">
      <h1 className="mb-6 text-2xl font-semibold text-ui-text dark:text-ui-dark-text">Settings</h1>
      <section aria-labelledby="theme-heading">
        <h2
          id="theme-heading"
          className="mb-2 text-base font-medium text-ui-text dark:text-ui-dark-text"
        >
          Theme
        </h2>
        <div
          role="radiogroup"
          aria-labelledby="theme-heading"
          className="flex gap-2 rounded-ui-lg bg-ui-bg-tertiary p-1 dark:bg-ui-dark-bg-secondary"
        >
          {THEME_CHOICES.map((choice) => {
            const on = theme === choice
            return (
              <label
                key={choice}
                className={[
                  'flex min-h-touch flex-1 cursor-pointer flex-col items-center justify-center',
                  'rounded-ui px-3 py-2 text-center no-select',
                  'focus-within:ring-2 focus-within:ring-primary-400',
                  on
                    ? 'bg-ui-bg text-ui-text shadow-ui-sm dark:bg-ui-dark-bg-tertiary dark:text-ui-dark-text'
                    : 'text-ui-text-secondary dark:text-ui-dark-text-secondary',
                ].join(' ')}
              >
                <input
                  type="radio"
                  name="theme"
                  value={choice}
                  checked={on}
                  onChange={() => choose(choice)}
                  className="sr-only"
                />
                <span className="text-sm font-semibold">{LABELS[choice].name}</span>
                <span className="text-xs opacity-80">{LABELS[choice].hint}</span>
              </label>
            )
          })}
        </div>
      </section>
    </main>
  )
}
