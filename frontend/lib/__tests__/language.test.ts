/**
 * The display language choice (Post-MVP frontier item 13): English or Suomi, per device.
 */

import { act, renderHook } from '@testing-library/react'
import { LANGUAGE_CHOICES, LANGUAGE_KEY, readLanguage, saveLanguage, useLanguage } from '../language'

beforeEach(() => {
  window.localStorage.clear()
})

describe('language', () => {
  it('is English until the cook picks one', () => {
    expect(readLanguage()).toBe('en')
  })

  it('offers English and Finnish', () => {
    expect(LANGUAGE_CHOICES).toEqual(['en', 'fi'])
  })

  it('persists the choice on this device', () => {
    saveLanguage('fi')
    expect(window.localStorage.getItem(LANGUAGE_KEY)).toBe('fi')
    expect(readLanguage()).toBe('fi')
  })

  it('clears storage for English, same as the theme does for System', () => {
    saveLanguage('fi')
    saveLanguage('en')
    expect(window.localStorage.getItem(LANGUAGE_KEY)).toBeNull()
    expect(readLanguage()).toBe('en')
  })

  it('ignores a stored value it does not know', () => {
    window.localStorage.setItem(LANGUAGE_KEY, 'sv')
    expect(readLanguage()).toBe('en')
  })

  it('survives storage that throws', () => {
    const get = jest.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    const set = jest.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    try {
      expect(readLanguage()).toBe('en')
      expect(() => saveLanguage('fi')).not.toThrow()
    } finally {
      get.mockRestore()
      set.mockRestore()
    }
  })

  describe('useLanguage', () => {
    it('starts English, then picks up the stored choice once mounted', () => {
      window.localStorage.setItem(LANGUAGE_KEY, 'fi')
      const { result } = renderHook(() => useLanguage())

      expect(result.current[0]).toBe('fi')
    })

    it('setting it saves and re-renders', () => {
      const { result } = renderHook(() => useLanguage())

      act(() => result.current[1]('fi'))

      expect(result.current[0]).toBe('fi')
      expect(window.localStorage.getItem(LANGUAGE_KEY)).toBe('fi')
    })
  })
})
