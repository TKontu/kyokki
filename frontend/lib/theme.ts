/**
 * The theme choice (Q31): System, Light or Dark.
 *
 * A per-device preference - the kitchen iPad is one device - kept in `localStorage` and applied
 * as `.light` or `.dark` on `<html>`, which the Tailwind `darkMode` variant and `globals.css`
 * already honour over `prefers-color-scheme`. System removes both classes, so the device's own
 * appearance decides. `THEME_SCRIPT` is inlined in the layout's `<head>` so the stored choice
 * is on `<html>` before the first paint and a dark kitchen never flashes white.
 *
 * Forcing the theme also has to move `<meta name="theme-color">` (round 2026-09-30-1):
 * `layout.tsx`'s `viewport.themeColor` renders one tag per `prefers-color-scheme` media query,
 * so on a light iPad with Dark forced the Home Screen status bar stayed light over a dark page.
 * `setThemeColor` overrides those with the forced colour; System removes the override and
 * leaves the two media-query tags - and the OS - in charge, same as the class.
 */

import { THEME_COLOR_DARK, THEME_COLOR_LIGHT } from './brand'

export type ThemeChoice = 'system' | 'light' | 'dark'

export const THEME_CHOICES: ThemeChoice[] = ['system', 'light', 'dark']

export const THEME_KEY = 'kyokki.theme'

function isChoice(value: unknown): value is ThemeChoice {
  return value === 'system' || value === 'light' || value === 'dark'
}

/** The stored choice on this device; System when there is none or storage is unavailable. */
export function readTheme(): ThemeChoice {
  try {
    const stored = window.localStorage.getItem(THEME_KEY)
    return isChoice(stored) ? stored : 'system'
  } catch {
    return 'system'
  }
}

/** The id of the `<meta name="theme-color">` `setThemeColor` adds to override System's pair. */
export const THEME_COLOR_META_ID = 'theme-color-forced'

/**
 * Overrides `<meta name="theme-color">` for a forced theme, so the Home Screen status bar
 * matches it instead of the device's own appearance. System removes the override.
 */
export function setThemeColor(choice: ThemeChoice, doc: Document = document): void {
  const existing = doc.getElementById(THEME_COLOR_META_ID)
  if (choice === 'system') {
    existing?.remove()
    return
  }
  const meta = existing ?? doc.createElement('meta')
  meta.id = THEME_COLOR_META_ID
  meta.setAttribute('name', 'theme-color')
  meta.setAttribute('content', choice === 'dark' ? THEME_COLOR_DARK : THEME_COLOR_LIGHT)
  if (!existing) doc.head.prepend(meta)
}

/** Puts the choice on `<html>`: a class for Light or Dark, none for System. Moves the
 * status bar colour with it (`setThemeColor`), both here (the toggle) and in `THEME_SCRIPT`
 * (before hydration). */
export function applyTheme(choice: ThemeChoice, root: HTMLElement = document.documentElement) {
  root.classList.remove('light', 'dark')
  if (choice !== 'system') root.classList.add(choice)
  setThemeColor(choice, root.ownerDocument)
}

/** Applies the choice and keeps it on this device. Storage failing only loses the keeping. */
export function saveTheme(choice: ThemeChoice) {
  applyTheme(choice)
  try {
    if (choice === 'system') window.localStorage.removeItem(THEME_KEY)
    else window.localStorage.setItem(THEME_KEY, choice)
  } catch {
    // Private mode or blocked storage: the choice holds until the page reloads
  }
}

/** What the screen shows for a choice, given whether the device prefers dark. */
export function effectiveTheme(choice: ThemeChoice, prefersDark: boolean): 'light' | 'dark' {
  if (choice === 'system') return prefersDark ? 'dark' : 'light'
  return choice
}

/**
 * Runs in `<head>` before the body paints. Self-contained - it cannot import - and it must
 * never throw, or it would stop the page's other inline scripts. Sets the same status-bar
 * override `setThemeColor` would, since that (a real import) cannot run until hydration.
 */
export const THEME_SCRIPT = `(function(){try{var t=localStorage.getItem(${JSON.stringify(
  THEME_KEY
)});if(t==='light'||t==='dark'){var c=document.documentElement.classList;c.remove('light','dark');c.add(t);var m=document.getElementById(${JSON.stringify(
  THEME_COLOR_META_ID
)});if(!m){m=document.createElement('meta');m.id=${JSON.stringify(
  THEME_COLOR_META_ID
)};m.setAttribute('name','theme-color');document.head.prepend(m)}m.setAttribute('content',t==='dark'?${JSON.stringify(
  THEME_COLOR_DARK
)}:${JSON.stringify(THEME_COLOR_LIGHT)})}}catch(e){}})()`
