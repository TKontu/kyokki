/**
 * The theme choice (Q31): System, Light or Dark, per device, applied as a class on <html>.
 */

import {
  THEME_KEY,
  THEME_SCRIPT,
  applyTheme,
  effectiveTheme,
  readTheme,
  saveTheme,
} from '../theme'

const root = () => document.documentElement

beforeEach(() => {
  window.localStorage.clear()
  root().classList.remove('light', 'dark')
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

  it('follows the media query when System', () => {
    expect(effectiveTheme('system', true)).toBe('dark')
    expect(effectiveTheme('system', false)).toBe('light')
    expect(effectiveTheme('light', true)).toBe('light')
    expect(effectiveTheme('dark', false)).toBe('dark')
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
})
