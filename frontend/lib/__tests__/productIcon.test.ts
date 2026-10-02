/**
 * The one precedence rule for a product icon (Q18-G2): the exact emoji first, then the
 * generated image, then the category emoji. A `proposed` emoji is never shown.
 */

import { productIconGlyph, resolveProductIcon } from '../productIcon'

describe('resolveProductIcon', () => {
  it('shows the emoji when the match is exact', () => {
    const icon = resolveProductIcon({
      emoji: '🧀',
      emojiMatch: 'exact',
      iconVersion: 1790000000,
      categoryIcon: '🥩',
    })

    expect(icon).toEqual({ kind: 'emoji', value: '🧀' })
  })

  it('shows the emoji when the cook set it', () => {
    const icon = resolveProductIcon({
      emoji: '🥨',
      emojiMatch: 'cook',
      iconVersion: null,
      categoryIcon: '🥩',
    })

    expect(icon).toEqual({ kind: 'emoji', value: '🥨' })
  })

  it('never shows a proposed emoji', () => {
    const icon = resolveProductIcon({
      emoji: '🥨',
      emojiMatch: 'proposed',
      iconVersion: 1790000000,
      categoryIcon: '🥩',
    })

    expect(icon).toEqual({ kind: 'generated', version: 1790000000 })
  })

  it('never shows a none or cleared emoji', () => {
    for (const emojiMatch of ['none', 'cleared'] as const) {
      const icon = resolveProductIcon({
        emoji: null,
        emojiMatch,
        iconVersion: null,
        categoryIcon: '🥩',
      })

      expect(icon).toEqual({ kind: 'category', value: '🥩' })
    }
  })

  it('falls back to the generated image when there is no exact emoji', () => {
    const icon = resolveProductIcon({
      emoji: null,
      emojiMatch: 'none',
      iconVersion: 1790000000,
      categoryIcon: '🥩',
    })

    expect(icon).toEqual({ kind: 'generated', version: 1790000000 })
  })

  it('falls back to the category emoji when there is neither', () => {
    const icon = resolveProductIcon({
      emoji: null,
      emojiMatch: null,
      iconVersion: null,
      categoryIcon: '🥩',
    })

    expect(icon).toEqual({ kind: 'category', value: '🥩' })
  })

  it('is none when nothing at all is available', () => {
    const icon = resolveProductIcon({
      emoji: null,
      emojiMatch: null,
      iconVersion: null,
      categoryIcon: null,
    })

    expect(icon).toEqual({ kind: 'none' })
  })

  it('trusts a tile-shaped input with no emojiMatch (already gated server-side)', () => {
    const icon = resolveProductIcon({
      emoji: '🧀',
      iconVersion: 1790000000,
      categoryIcon: '🥩',
    })

    expect(icon).toEqual({ kind: 'emoji', value: '🧀' })
  })
})

describe('productIconGlyph', () => {
  it('returns the emoji value', () => {
    expect(productIconGlyph({ kind: 'emoji', value: '🧀' }, '🥩')).toBe('🧀')
  })

  it('returns the category value', () => {
    expect(productIconGlyph({ kind: 'category', value: '🥩' }, '🥩')).toBe('🥩')
  })

  it('falls back to the raw category icon for a generated or none icon', () => {
    expect(productIconGlyph({ kind: 'generated', version: 1 }, '🥩')).toBe('🥩')
    expect(productIconGlyph({ kind: 'none' }, '🥩')).toBe('🥩')
  })

  it('is an empty string when there is nothing at all', () => {
    expect(productIconGlyph({ kind: 'none' }, null)).toBe('')
  })
})
