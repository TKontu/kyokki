'use client'

/**
 * Settings (Q33): reached from the "⋯" at the end of the app bar, not a main destination.
 *
 * The first setting is the theme (Q31): System follows the iPad's own appearance, Light and
 * Dark force one. It is a per-device choice, kept on this device (`lib/theme`), because the
 * kitchen iPad is the device that matters and a phone should keep its own.
 *
 * The second is the display language (Post-MVP frontier item 13, operator ruling
 * 2026-10-02): English shows each product's own (canonical) name, Suomi shows its Finnish
 * name where one exists, falling back to English otherwise. Same per-device pattern
 * (`lib/language`) - a phone keeps its own choice too. Phase 1 ships this and the product
 * names it affects; translating the app's own UI text is a later round.
 *
 * Icon curation (operator ask 2026-10-03) adds "Canonical icons", shown only on a develop
 * build (`GET /api/icon-library/status`'s `curation_enabled`) - the operator's own build,
 * not every deployment. It lists every icon the cook marked on the product sheet
 * (thumbnail, name, Unmark) and offers Download bundle, the zip
 * `backend/scripts/apply_icon_bundle.py` merges into the repo's icon library for a PR
 * (`docs/icon_library/README.md`).
 */

import { useEffect, useState } from 'react'
import Button from '@/components/ui/Button'
import { bundleUrl } from '@/lib/api/iconLibrary'
import { iconUrl } from '@/lib/api/products'
import { useIconLibraryMarks, useIconLibraryStatus, useUnmarkIcon } from '@/hooks/useIconLibrary'
import { useT } from '@/lib/i18n'
import { LANGUAGE_CHOICES, readLanguage, saveLanguage, type Language } from '@/lib/language'
import { readTheme, saveTheme, THEME_CHOICES, type ThemeChoice } from '@/lib/theme'

export default function SettingsPage() {
  const [theme, setTheme] = useState<ThemeChoice>('system')
  const [language, setLanguage] = useState<Language>('en')
  const { t } = useT()
  const curationStatus = useIconLibraryStatus()
  const curationEnabled = curationStatus.data?.curation_enabled ?? false
  const marks = useIconLibraryMarks(curationEnabled)
  const unmark = useUnmarkIcon()

  const labels: Record<ThemeChoice, { name: string; hint: string }> = {
    system: { name: t('settings.theme.system.name'), hint: t('settings.theme.system.hint') },
    light: { name: t('settings.theme.light.name'), hint: t('settings.theme.light.hint') },
    dark: { name: t('settings.theme.dark.name'), hint: t('settings.theme.dark.hint') },
  }

  const languageLabels: Record<Language, { name: string; hint: string }> = {
    en: { name: t('settings.language.en.name'), hint: t('settings.language.en.hint') },
    fi: { name: t('settings.language.fi.name'), hint: t('settings.language.fi.hint') },
  }

  // Read after mounting: the server cannot know what this device stored
  useEffect(() => {
    setTheme(readTheme())
    setLanguage(readLanguage())
  }, [])

  const choose = (choice: ThemeChoice) => {
    setTheme(choice)
    saveTheme(choice)
  }

  const chooseLanguage = (choice: Language) => {
    setLanguage(choice)
    saveLanguage(choice)
  }

  return (
    <main className="mx-auto w-full max-w-xl px-4 py-6">
      <h1 className="mb-6 text-2xl font-semibold text-ui-text dark:text-ui-dark-text">
        {t('settings.title')}
      </h1>
      <section aria-labelledby="language-heading" className="mb-6">
        <h2
          id="language-heading"
          className="mb-2 text-base font-medium text-ui-text dark:text-ui-dark-text"
        >
          {t('settings.language.heading')}
        </h2>
        <div
          role="radiogroup"
          aria-labelledby="language-heading"
          className="flex gap-2 rounded-ui-lg bg-ui-bg-tertiary p-1 dark:bg-ui-dark-bg-secondary"
        >
          {LANGUAGE_CHOICES.map((choice) => {
            const on = language === choice
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
                  name="language"
                  value={choice}
                  checked={on}
                  onChange={() => chooseLanguage(choice)}
                  className="sr-only"
                />
                <span className="text-sm font-semibold">{languageLabels[choice].name}</span>
                <span className="text-xs opacity-80">{languageLabels[choice].hint}</span>
              </label>
            )
          })}
        </div>
      </section>
      <section aria-labelledby="theme-heading">
        <h2
          id="theme-heading"
          className="mb-2 text-base font-medium text-ui-text dark:text-ui-dark-text"
        >
          {t('settings.theme.heading')}
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
                <span className="text-sm font-semibold">{labels[choice].name}</span>
                <span className="text-xs opacity-80">{labels[choice].hint}</span>
              </label>
            )
          })}
        </div>
      </section>
      {curationEnabled && (
        <section aria-labelledby="canonical-icons-heading" className="mt-6">
          <h2
            id="canonical-icons-heading"
            className="mb-2 text-base font-medium text-ui-text dark:text-ui-dark-text"
          >
            {t('settings.canonicalIcons.heading')}
          </h2>
          {marks.data && marks.data.length > 0 ? (
            <>
              <p className="mb-2 text-xs text-ui-text-secondary dark:text-ui-dark-text-secondary">
                {t('settings.canonicalIcons.count', { count: marks.data.length })}
              </p>
              <ul className="divide-y divide-ui-border rounded-ui-lg border border-ui-border dark:divide-ui-dark-border dark:border-ui-dark-border">
                {marks.data.map((entry) => (
                  <li key={entry.id} className="flex items-center gap-3 p-2">
                    {entry.icon_version != null ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={iconUrl(entry.id, entry.icon_version)}
                        alt=""
                        aria-hidden="true"
                        width={32}
                        height={32}
                        className="h-8 w-8 shrink-0 rounded-ui border border-ui-border dark:border-ui-dark-border"
                      />
                    ) : (
                      <div className="h-8 w-8 shrink-0 rounded-ui border border-ui-border dark:border-ui-dark-border" />
                    )}
                    <span className="flex-1 text-sm text-ui-text dark:text-ui-dark-text">
                      {entry.name}
                    </span>
                    <Button
                      variant="ghost"
                      size="sm"
                      loading={unmark.isPending}
                      onClick={() => unmark.mutate(entry.id)}
                    >
                      {t('settings.canonicalIcons.unmark')}
                    </Button>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary">
              {t('settings.canonicalIcons.empty')}
            </p>
          )}
          <a
            href={bundleUrl()}
            className="mt-3 inline-flex min-h-touch items-center justify-center rounded-ui border border-ui-border px-4 text-sm font-medium text-ui-text no-select dark:border-ui-dark-border dark:text-ui-dark-text"
          >
            {t('settings.canonicalIcons.downloadBundle')}
          </a>
        </section>
      )}
    </main>
  )
}
