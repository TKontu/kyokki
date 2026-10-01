/**
 * The theme choice (Q31): System, Light or Dark, per device, applied as a class on <html>.
 */

import { THEME_COLOR_DARK, THEME_COLOR_LIGHT } from '../brand'
import {
  THEME_KEY,
  THEME_SCRIPT,
  applyTheme,
  effectiveTheme,
  readTheme,
  saveTheme,
  setThemeColor,
} from '../theme'

const root = () => document.documentElement

/** The pair Next renders from `viewport.themeColor` in `layout.tsx` - not anything our own
 * code creates (see `setThemeColor`'s docstring), so tests build them the way Next would. */
function addThemeColorMetas(): void {
  for (const [media, content] of [
    ['(prefers-color-scheme: light)', THEME_COLOR_LIGHT],
    ['(prefers-color-scheme: dark)', THEME_COLOR_DARK],
  ] as const) {
    const meta = document.createElement('meta')
    meta.setAttribute('name', 'theme-color')
    meta.setAttribute('media', media)
    meta.setAttribute('content', content)
    document.head.appendChild(meta)
  }
}

function themeColorMetas(): HTMLMetaElement[] {
  return Array.from(document.querySelectorAll('meta[name="theme-color"]'))
}

beforeEach(() => {
  window.localStorage.clear()
  root().classList.remove('light', 'dark')
  document.head.innerHTML = ''
  addThemeColorMetas()
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
    it('rewrites both existing tags to the forced colour, never adding a third', () => {
      setThemeColor('dark')
      const metas = themeColorMetas()
      expect(metas).toHaveLength(2)
      for (const meta of metas) expect(meta).toHaveAttribute('content', THEME_COLOR_DARK)

      setThemeColor('light')
      expect(themeColorMetas()).toHaveLength(2)
      for (const meta of themeColorMetas()) {
        expect(meta).toHaveAttribute('content', THEME_COLOR_LIGHT)
      }
    })

    it('restores each tag to its own colour for System', () => {
      setThemeColor('dark')
      setThemeColor('system')
      const [light, dark] = themeColorMetas()
      expect(light).toHaveAttribute('content', THEME_COLOR_LIGHT)
      expect(dark).toHaveAttribute('content', THEME_COLOR_DARK)
    })

    it('does nothing if the tags are not there yet, rather than adding one', () => {
      document.head.innerHTML = ''
      expect(() => setThemeColor('dark')).not.toThrow()
      expect(themeColorMetas()).toHaveLength(0)
    })
  })

  it('moves the status-bar colour with the class when the theme is forced (applyTheme)', () => {
    applyTheme('dark')
    for (const meta of themeColorMetas()) expect(meta).toHaveAttribute('content', THEME_COLOR_DARK)

    applyTheme('light')
    for (const meta of themeColorMetas()) {
      expect(meta).toHaveAttribute('content', THEME_COLOR_LIGHT)
    }

    applyTheme('system')
    const [light, dark] = themeColorMetas()
    expect(light).toHaveAttribute('content', THEME_COLOR_LIGHT)
    expect(dark).toHaveAttribute('content', THEME_COLOR_DARK)
  })

  it("moves the status-bar colour on toggle too (saveTheme, the settings page's path)", () => {
    saveTheme('dark')
    for (const meta of themeColorMetas()) expect(meta).toHaveAttribute('content', THEME_COLOR_DARK)
  })

  it('leaves theme-color alone: the boot script only ever touches the class', () => {
    // setThemeColor cannot run from the boot script without risking a hydration mismatch on
    // tags that carry no suppressHydrationWarning of their own (see the module docstring);
    // the mount effect in app/providers.tsx is what sets the forced colour, after hydration.
    window.localStorage.setItem(THEME_KEY, 'dark')
    new Function(THEME_SCRIPT)()

    expect(root()).toHaveClass('dark')
    const [light, dark] = themeColorMetas()
    expect(light).toHaveAttribute('content', THEME_COLOR_LIGHT)
    expect(dark).toHaveAttribute('content', THEME_COLOR_DARK)
  })
})
