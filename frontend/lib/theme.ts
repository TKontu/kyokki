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
 * `setThemeColor` rewrites the `content` of those same two tags to the forced colour, rather
 * than adding a third one - a first attempt did that, and a boot script inserting a `<head>`
 * child before hydration shifts React's tag-based matching of every sibling after it by one,
 * breaking hydration (a review of round 2026-09-30-1 reproduced it: with a stored `dark`
 * theme, hydration failed and silently reverted both the class and the colour).
 *
 * `setThemeColor` still is not called from `THEME_SCRIPT`, even rewriting in place: the two
 * tags have no `suppressHydrationWarning` of their own (Next generates them from the
 * `viewport` export, not JSX of ours to add it to), so a value changed on them before
 * hydration logs a mismatch and React patches it back to the unforced colour anyway. Instead
 * a mount effect in `providers.tsx` calls `applyTheme(readTheme())` once hydration has
 * actually finished, which sets the forced colour (and heals the class too, belt and braces,
 * if a hydration mismatch ever reverts that instead).
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

/**
 * Next renders these two from `viewport.themeColor` in `layout.tsx` - one per
 * `prefers-color-scheme` media query. Selected by `media`, not position, since metadata tags
 * and the boot script's place in `<head>` are Next's to order, not ours.
 */
function themeColorMetas(doc: Document): { light: Element | null; dark: Element | null } {
  return {
    light: doc.querySelector('meta[name="theme-color"][media*="light"]'),
    dark: doc.querySelector('meta[name="theme-color"][media*="dark"]'),
  }
}

/**
 * Rewrites the `content` of Next's two existing `theme-color` tags for a forced theme, so the
 * Home Screen status bar matches it instead of the device's own appearance; both become the
 * same colour, so which one a browser's media query matches makes no difference. System
 * restores each to its own colour. Never adds or removes a tag (see the module docstring).
 */
export function setThemeColor(choice: ThemeChoice, doc: Document = document): void {
  const { light, dark } = themeColorMetas(doc)
  if (choice === 'system') {
    light?.setAttribute('content', THEME_COLOR_LIGHT)
    dark?.setAttribute('content', THEME_COLOR_DARK)
    return
  }
  const color = choice === 'dark' ? THEME_COLOR_DARK : THEME_COLOR_LIGHT
  light?.setAttribute('content', color)
  dark?.setAttribute('content', color)
}

/** Puts the choice on `<html>`: a class for Light or Dark, none for System. Moves the status
 * bar colour with it (`setThemeColor`) - called from here on toggle, and from a mount effect
 * in `providers.tsx` once hydration has finished (`THEME_SCRIPT` cannot call it: see the
 * module docstring). */
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
 * never throw, or it would stop the page's other inline scripts.
 *
 * It only ever touches the `class` on `<html>`, which `suppressHydrationWarning` there (see
 * `layout.tsx`) was already covering before this round. It deliberately leaves the
 * `theme-color` tags alone: unlike that class, they carry no `suppressHydrationWarning` (Next
 * generates them from the `viewport` export, not from JSX we write), so changing their
 * `content` here - even just the value, with no tag added or removed - would still hydrate as
 * a mismatch React logs and then overwrites back to the unforced colour. The mount effect in
 * `providers.tsx` sets the forced colour once hydration has actually finished, which is also
 * what repairs it if hydration mismatches for any other reason.
 */
export const THEME_SCRIPT = `(function(){try{var t=localStorage.getItem(${JSON.stringify(
  THEME_KEY
)});if(t==='light'||t==='dark'){var c=document.documentElement.classList;c.remove('light','dark');c.add(t)}}catch(e){}})()`
