'use client'

/**
 * The display language choice (Post-MVP frontier item 13).
 *
 * `'use client'`: `useLanguage` uses hooks, and `layout.tsx` (a Server Component) imports
 * `LANGUAGE_SCRIPT` from this same module for its boot script - a plain string, no hook
 * involved, but without this directive Next's compiler still flags the file for importing
 * `useState`/`useEffect` into a Server Component's import graph. `lib/theme.ts` never needed
 * this because it has no hooks at all; this module does.
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
 *
 * Phase 2 (`lib/i18n`) translates the app's own UI text too, and needs this choice to reach a
 * component that never remounts - the app shell's nav is in `layout.tsx`, outside every route,
 * so a language switch on the Settings page has to reach it without a navigation in between.
 * `saveLanguage` dispatches `LANGUAGE_EVENT`; `useLanguage` (and `lib/i18n`'s `useT`) listens
 * for it, the same `window.addEventListener`/`dispatchEvent` pattern a cross-tab `storage`
 * event already uses, so every mounted consumer re-renders, not just the one that set it.
 */

import { useCallback, useEffect, useState } from 'react'

export type Language = 'en' | 'fi'

export const LANGUAGE_CHOICES: Language[] = ['en', 'fi']

export const LANGUAGE_KEY = 'kyokki.language'

/** Fired on `window` after a save, this tab or another; see the module docstring. */
export const LANGUAGE_EVENT = 'kyokki:language'

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

/** Keeps the choice on this device, and tells every mounted consumer in this tab (and, via
 * `storage`, every other tab) to re-read it. Storage failing only loses the keeping - the
 * event still fires, so this tab's own components still pick up the in-memory choice. */
export function saveLanguage(choice: Language): void {
  try {
    if (choice === 'en') window.localStorage.removeItem(LANGUAGE_KEY)
    else window.localStorage.setItem(LANGUAGE_KEY, choice)
  } catch {
    // Private mode or blocked storage: the choice holds until the page reloads
  } finally {
    try {
      window.dispatchEvent(new Event(LANGUAGE_EVENT))
    } catch {
      // No window (SSR): nothing mounted yet to tell
    }
  }
}

/** Calls `onChange` whenever the choice might have moved - this tab's own `saveLanguage`, or
 * another tab's (the native `storage` event) - and returns the unsubscribe. */
export function subscribeToLanguage(onChange: () => void): () => void {
  if (typeof window === 'undefined') return () => {}
  window.addEventListener(LANGUAGE_EVENT, onChange)
  window.addEventListener('storage', onChange)
  return () => {
    window.removeEventListener(LANGUAGE_EVENT, onChange)
    window.removeEventListener('storage', onChange)
  }
}

/**
 * The current device's language choice, and a setter that also keeps it.
 *
 * Reads after mounting, like the settings page already does for the theme: the server cannot
 * know what this device stored, so every consumer (a tile, an item sheet, the products list)
 * starts at `'en'` and picks up the stored choice once mounted. A mounted consumer also follows
 * a *later* change - its own `setLanguage`, another component's, or another tab's - without
 * needing a fresh mount, which is what lets the app shell's nav (outside every route) update
 * right after a Settings change (see the module docstring).
 */
export function useLanguage(): [Language, (choice: Language) => void] {
  const [language, setLanguageState] = useState<Language>('en')

  useEffect(() => {
    setLanguageState(readLanguage())
    return subscribeToLanguage(() => setLanguageState(readLanguage()))
  }, [])

  const setLanguage = useCallback((choice: Language) => {
    saveLanguage(choice)
    setLanguageState(choice)
  }, [])

  return [language, setLanguage]
}

/** Puts the choice on `<html lang>`: the attribute `tsc`-checked translations (`lib/i18n`)
 * promise to follow. Called from a mount effect in `providers.tsx`, same as `applyTheme` for
 * the theme class - not from `LANGUAGE_SCRIPT`, which only avoids a flash of the wrong
 * `class`; `lang` carries no visible flash to avoid, and setting it before hydration would
 * only risk the same mismatch `theme.ts`'s docstring describes for the theme-colour tags. */
export function applyLanguage(choice: Language, root: HTMLElement = document.documentElement) {
  root.lang = choice
}

/**
 * Runs in `<head>` before the body paints, the same shape as `THEME_SCRIPT`: self-contained,
 * never throws. Unlike the theme class, `<html lang="en">` from `layout.tsx` is already
 * correct for the default and every first visit, so this only has anything to do once a
 * cook has actually chosen Finnish - a plain early exit, not a mismatch to suppress.
 */
export const LANGUAGE_SCRIPT = `(function(){try{var l=localStorage.getItem(${JSON.stringify(
  LANGUAGE_KEY
)});if(l==='fi')document.documentElement.lang=l}catch(e){}})()`
