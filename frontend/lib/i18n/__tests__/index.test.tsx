/**
 * The app's own UI text (Post-MVP frontier item 13, phase 2): the catalogue lookup,
 * interpolation and plural selection `useT()` wraps, plus the depth-first check that `fi` has
 * every key `en` has (the runtime half of what `tsc` already checks via `Messages`).
 */

import { act, renderHook } from '@testing-library/react'
import { en } from '../en'
import { fi } from '../fi'
import { formatDate, formatNumber, localeFor, useT } from '../index'
import { LANGUAGE_KEY, saveLanguage } from '@/lib/language'

type Leaf = string | { one: string; other: string }

/** Every dotted path to a leaf (a string, or a `{one, other}` pair) in a catalogue. */
function leafPaths(node: unknown, prefix = ''): string[] {
  if (typeof node === 'string') return [prefix]
  if (node && typeof node === 'object') {
    const record = node as Record<string, unknown>
    if (typeof record.one === 'string' && typeof record.other === 'string') return [prefix]
    return Object.keys(record).flatMap((key) =>
      leafPaths(record[key], prefix ? `${prefix}.${key}` : key)
    )
  }
  return []
}

function at(node: unknown, path: string): Leaf | undefined {
  return path.split('.').reduce<unknown>((current, part) => {
    if (typeof current !== 'object' || current === null) return undefined
    return (current as Record<string, unknown>)[part]
  }, node) as Leaf | undefined
}

beforeEach(() => {
  window.localStorage.clear()
})

describe('fi has every key en has', () => {
  const paths = leafPaths(en)

  it('is not empty (the walk itself found something)', () => {
    expect(paths.length).toBeGreaterThan(20)
  })

  it.each(paths)('%s', (path) => {
    const english = at(en, path)
    const finnish = at(fi, path)
    expect(finnish).toBeDefined()
    if (typeof english === 'string') {
      expect(typeof finnish).toBe('string')
    } else {
      expect(finnish).toMatchObject({ one: expect.any(String), other: expect.any(String) })
    }
  })
})

describe('useT', () => {
  it('reads English by default', () => {
    const { result } = renderHook(() => useT())

    expect(result.current.t('shopping.header.title')).toBe('Shopping')
    expect(result.current.language).toBe('en')
  })

  it('reads Finnish once the device has chosen it', () => {
    window.localStorage.setItem(LANGUAGE_KEY, 'fi')
    const { result } = renderHook(() => useT())

    expect(result.current.t('shopping.header.title')).toBe('Ostoslista')
    expect(result.current.language).toBe('fi')
  })

  it('follows a later change without remounting (the shell nav case)', () => {
    const { result } = renderHook(() => useT())
    expect(result.current.t('gone.title')).toBe('Gone')

    act(() => {
      saveLanguage('fi')
    })

    expect(result.current.t('gone.title')).toBe('Käytetty')
  })

  it('interpolates a named placeholder', () => {
    const { result } = renderHook(() => useT())

    expect(result.current.t('shopping.itemRow.remove', { name: 'Bananas' })).toBe(
      'Remove Bananas'
    )
  })

  it('leaves an unsupplied placeholder as literal text rather than blanking it', () => {
    const { result } = renderHook(() => useT())

    expect(result.current.t('shopping.itemRow.remove')).toBe('Remove {name}')
  })

  it('picks the plural form by count: one in English', () => {
    const { result } = renderHook(() => useT())

    expect(result.current.t('shopping.clearedToast', { count: 1 })).toBe('Cleared 1 item')
    expect(result.current.t('shopping.clearedToast', { count: 3 })).toBe('Cleared 3 items')
  })

  it('picks the plural form by Finnish numeral agreement', () => {
    window.localStorage.setItem(LANGUAGE_KEY, 'fi')
    const { result } = renderHook(() => useT())

    expect(result.current.t('shopping.clearedToast', { count: 1 })).toBe('Poistettu 1 kohde')
    expect(result.current.t('shopping.clearedToast', { count: 3 })).toBe('Poistettu 3 kohdetta')
  })

  it('falls back to the key itself for one it cannot find, rather than throwing', () => {
    const { result } = renderHook(() => useT())

    expect(result.current.t('nowhere.at.all')).toBe('nowhere.at.all')
  })
})

describe('locale-driven formatting', () => {
  it('names the Intl locale per language, en-GB and fi-FI', () => {
    expect(localeFor('en')).toBe('en-GB')
    expect(localeFor('fi')).toBe('fi-FI')
  })

  it('formats a decimal with the locale\'s own separator', () => {
    expect(formatNumber(2.5, 'en')).toBe('2.5')
    expect(formatNumber(2.5, 'fi')).toBe('2,5')
  })

  it('formats a date in each locale\'s own word order', () => {
    expect(formatDate('2026-10-03', 'en')).toBe('3 October 2026')
    expect(formatDate('2026-10-03', 'fi')).toBe('3. lokakuuta 2026')
  })
})
