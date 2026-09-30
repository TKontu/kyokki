/**
 * The theme choice (Q31): System, Light or Dark, per device, applied as a class on <html>.
 */

import { THEME_COLOR_DARK, THEME_COLOR_LIGHT } from '../brand'
import {
  THEME_COLOR_META_ID,
  THEME_KEY,
  THEME_SCRIPT,
  applyTheme,
  effectiveTheme,
  readTheme,
  saveTheme,
  setThemeColor,
} from '../theme'

const root = () => document.documentElement

function themeColorMeta(): HTMLMetaElement | null {
  return document.getElementById(THEME_COLOR_META_ID) as HTMLMetaElement | null
}

beforeEach(() => {
  window.localStorage.clear()
  root().classList.remove('light', 'dark')
  themeColorMeta()?.remove()
})

describe('theme', () => {
  it('is System until the cook picks one', () => {
    expect(readTheme()).toBe('system')
  })

  it('forces light or dark with a class on <html>', () => {
    applyTheme('dark')
    expect(root()).toHaveClass('dark')
    expect(root()).not.toHaveClass('light')

    applyTheme('light')
    expect(root()).toHaveClass('light')
    expect(root()).not.toHaveClass('dark')
  })

  it('clears the class for System, so the device appearance decides', () => {
    applyTheme('dark')
    applyTheme('system')
    expect(root()).not.toHaveClass('dark')
    expect(root()).not.toHaveClass('light')
  })

  it('persists the choice on this device and applies it', () => {
    saveTheme('dark')
    expect(window.localStorage.getItem(THEME_KEY)).toBe('dark')
    expect(readTheme()).toBe('dark')
    expect(root()).toHaveClass('dark')

    saveTheme('system')
    expect(window.localStorage.getItem(THEME_KEY)).toBeNull()
    expect(readTheme()).toBe('system')
  })

  it('ignores a stored value it does not know', () => {
    window.localStorage.setItem(THEME_KEY, 'sepia')
    expect(readTheme()).toBe('system')
  })

  it('survives storage that throws', () => {
    const get = jest.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    const set = jest.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    try {
      expect(readTheme()).toBe('system')
      expect(() => saveTheme('dark')).not.toThrow()
      expect(root()).toHaveClass('dark')
    } finally {
      get.mockRestore()
      set.mockRestore()
    }
  })

  it('follows the media query when System: no class survives to override it', () => {
    // effectiveTheme() is a pure helper - nothing in the app calls it - so it cannot stand
    // in for "System follows the media query" on its own; the real path is the class (or
    // its absence) that `:root:not(.light)` / Tailwind's `darkMode` variant actually read.
    expect(effectiveTheme('system', true)).toBe('dark')
    expect(effectiveTheme('system', false)).toBe('light')
    expect(effectiveTheme('light', true)).toBe('light')
    expect(effectiveTheme('dark', false)).toBe('dark')

    applyTheme('dark')
    applyTheme('system')
    expect(root().className).toBe('')
  })

  it('has a boot script that applies the stored choice before first paint', () => {
    window.localStorage.setItem(THEME_KEY, 'dark')
    // The script is inlined in <head>; running it must set the class on its own
    new Function(THEME_SCRIPT)()
    expect(root()).toHaveClass('dark')

    root().classList.remove('dark')
    window.localStorage.setItem(THEME_KEY, 'bogus')
    new Function(THEME_SCRIPT)()
    expect(root()).not.toHaveClass('dark')
    expect(root()).not.toHaveClass('light')
  })

  describe('setThemeColor', () => {
    it('overrides theme-color with the forced choice', () => {
      setThemeColor('dark')
      expect(themeColorMeta()).toHaveAttribute('content', THEME_COLOR_DARK)

      setThemeColor('light')
      expect(themeColorMeta()).toHaveAttribute('content', THEME_COLOR_LIGHT)
    })

    it('removes the override for System, leaving the media-query pair in charge', () => {
      setThemeColor('dark')
      setThemeColor('system')
      expect(themeColorMeta()).toBeNull()
    })

    it('updates the existing tag in place rather than adding a second one', () => {
      setThemeColor('dark')
      setThemeColor('light')
      expect(document.querySelectorAll(`#${THEME_COLOR_META_ID}`)).toHaveLength(1)
    })
  })

  it('moves the status-bar colour with the class when the theme is forced (applyTheme)', () => {
    applyTheme('dark')
    expect(themeColorMeta()).toHaveAttribute('content', THEME_COLOR_DARK)

    applyTheme('light')
    expect(themeColorMeta()).toHaveAttribute('content', THEME_COLOR_LIGHT)

    applyTheme('system')
    expect(themeColorMeta()).toBeNull()
  })

  it("moves the status-bar colour on toggle too (saveTheme, the settings page's path)", () => {
    saveTheme('dark')
    expect(themeColorMeta()).toHaveAttribute('content', THEME_COLOR_DARK)
  })

  it('sets the same status-bar override from the boot script, before hydration can', () => {
    window.localStorage.setItem(THEME_KEY, 'dark')
    new Function(THEME_SCRIPT)()
    expect(themeColorMeta()).toHaveAttribute('content', THEME_COLOR_DARK)

    themeColorMeta()?.remove()
    root().classList.remove('dark')
    window.localStorage.setItem(THEME_KEY, 'light')
    new Function(THEME_SCRIPT)()
    expect(themeColorMeta()).toHaveAttribute('content', THEME_COLOR_LIGHT)

    // System (no stored value): the script must not add an override
    themeColorMeta()?.remove()
    root().classList.remove('light')
    window.localStorage.removeItem(THEME_KEY)
    new Function(THEME_SCRIPT)()
    expect(themeColorMeta()).toBeNull()
  })
})
