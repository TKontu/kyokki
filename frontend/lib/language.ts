/**
 * The display language choice (Post-MVP frontier item 13).
 *
 * Operator ruling (2026-10-02): "the system should have selectable display language. But of
 * course if the receipts are finnish the input data should kept as original." Products are
 * generic and English (MVP-R2); this is a per-device preference - the same pattern as the
 * theme choice (`lib/theme.ts`) - that picks which language a product's `display_names` shows
 * in, with English (the canonical name) as the one choice that is never a lookup into that map.
 *
 * Phase 1 ships Finnish; the type and `LANGUAGE_CHOICES` are the one place a future language
 * is added, same as `THEME_CHOICES`. Receipt text (the printed line, review and audit) is
 * untouched by this: it is not display_names and never goes through `displayName()`.
 */

import { useEffect, useState } from 'react'

export type Language = 'en' | 'fi'

export const LANGUAGE_CHOICES: Language[] = ['en', 'fi']

export const LANGUAGE_KEY = 'kyokki.language'

function isLanguage(value: unknown): value is Language {
  return LANGUAGE_CHOICES.includes(value as Language)
}

/** The stored choice on this device; English when there is none or storage is unavailable. */
export function readLanguage(): Language {
  try {
    const stored = window.localStorage.getItem(LANGUAGE_KEY)
    return isLanguage(stored) ? stored : 'en'
  } catch {
    return 'en'
  }
}

/** Keeps the choice on this device. Storage failing only loses the keeping. */
export function saveLanguage(choice: Language): void {
  try {
    if (choice === 'en') window.localStorage.removeItem(LANGUAGE_KEY)
    else window.localStorage.setItem(LANGUAGE_KEY, choice)
  } catch {
    // Private mode or blocked storage: the choice holds until the page reloads
  }
}

/**
 * The current device's language choice, and a setter that also keeps it.
 *
 * Reads after mounting, like the settings page already does for the theme: the server cannot
 * know what this device stored, so every consumer (a tile, an item sheet, the products list)
 * starts at `'en'` and picks up the stored choice once mounted - which is also when a fresh
 * page (after Settings changed it) sees the new value, since each route is its own mount.
 */
export function useLanguage(): [Language, (choice: Language) => void] {
  const [language, setLanguageState] = useState<Language>('en')

  useEffect(() => {
    setLanguageState(readLanguage())
  }, [])

  const setLanguage = (choice: Language) => {
    saveLanguage(choice)
    setLanguageState(choice)
  }

  return [language, setLanguage]
}
