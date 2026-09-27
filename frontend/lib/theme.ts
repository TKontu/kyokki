/**
 * The theme choice (Q31): System, Light or Dark.
 *
 * A per-device preference - the kitchen iPad is one device - kept in `localStorage` and applied
 * as `.light` or `.dark` on `<html>`, which the Tailwind `darkMode` variant and `globals.css`
 * already honour over `prefers-color-scheme`. System removes both classes, so the device's own
 * appearance decides. `THEME_SCRIPT` is inlined in the layout's `<head>` so the stored choice
 * is on `<html>` before the first paint and a dark kitchen never flashes white.
 */

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

/** Puts the choice on `<html>`: a class for Light or Dark, none for System. */
export function applyTheme(choice: ThemeChoice, root: HTMLElement = document.documentElement) {
  root.classList.remove('light', 'dark')
  if (choice !== 'system') root.classList.add(choice)
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
 * never throw, or it would stop the page's other inline scripts.
 */
export const THEME_SCRIPT = `(function(){try{var t=localStorage.getItem(${JSON.stringify(
  THEME_KEY
)});if(t==='light'||t==='dark'){var c=document.documentElement.classList;c.remove('light','dark');c.add(t)}}catch(e){}})()`
