/**
 * The product name to show in the cook's chosen display language (Post-MVP frontier item 13).
 */

import { displayName } from '../displayName'

describe('displayName', () => {
  it('shows the canonical name in English, whatever the map carries', () => {
    expect(displayName({ fi: 'Maito' }, 'Milk', 'en')).toBe('Milk')
    expect(displayName(null, 'Milk', 'en')).toBe('Milk')
  })

  it('shows the language entry when one exists', () => {
    expect(displayName({ fi: 'Maito' }, 'Milk', 'fi')).toBe('Maito')
  })

  it('falls back to the canonical name when the language has no entry', () => {
    expect(displayName({}, 'Milk', 'fi')).toBe('Milk')
    expect(displayName(null, 'Milk', 'fi')).toBe('Milk')
    expect(displayName(undefined, 'Milk', 'fi')).toBe('Milk')
  })

  it('falls back when the entry is blank', () => {
    expect(displayName({ fi: '   ' }, 'Milk', 'fi')).toBe('Milk')
  })
})
