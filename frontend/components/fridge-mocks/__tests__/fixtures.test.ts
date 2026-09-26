/**
 * Sample stock for judging the mocks on an empty homelab (Q17-M): about two dozen items that
 * fill every area and every tier the fridge shows.
 */

import { AREAS, areaOf } from '@/lib/fridge'
import { stalenessOf } from '@/lib/staleness'
import { fixtureItems } from '../fixtures'

describe('fixtureItems', () => {
  it('holds about two dozen items', () => {
    const items = fixtureItems()
    expect(items.length).toBeGreaterThanOrEqual(22)
    expect(items.length).toBeLessThanOrEqual(32)
  })

  it('fills every area', () => {
    const areas = new Set(fixtureItems().map(areaOf))
    expect(Array.from(areas).sort()).toEqual(AREAS.map((area) => area.id).sort())
  })

  it('covers every tier the fridge shows', () => {
    const tiers = new Set(fixtureItems().map(stalenessOf))
    expect(Array.from(tiers).sort()).toEqual(['later', 'soon', 'stale', 'week'])
  })

  it('gives every item its own id', () => {
    const items = fixtureItems()
    expect(new Set(items.map((item) => item.id)).size).toBe(items.length)
  })
})
