import { boughtItems, groupOpenItems } from '../groupShoppingItems'
import type { ShoppingListItem } from '@/types/shopping'

function item(overrides: Partial<ShoppingListItem>): ShoppingListItem {
  return {
    id: 'i',
    product_master_id: null,
    name: 'Item',
    quantity: 1,
    unit: 'pcs',
    priority: 'normal',
    source: 'manual',
    is_purchased: false,
    added_at: '2026-10-01T10:00:00Z',
    purchased_at: null,
    ...overrides,
  }
}

describe('groupOpenItems', () => {
  it('groups open items urgent, then normal, then low', () => {
    const urgent = item({ id: 'u', priority: 'urgent' })
    const normal = item({ id: 'n', priority: 'normal' })
    const low = item({ id: 'l', priority: 'low' })

    const groups = groupOpenItems([low, normal, urgent])

    expect(groups.map((g) => g.key)).toEqual(['urgent', 'normal', 'low'])
    expect(groups[0].items).toEqual([urgent])
    expect(groups[1].items).toEqual([normal])
    expect(groups[2].items).toEqual([low])
  })

  it('leaves out an empty priority group', () => {
    const groups = groupOpenItems([item({ priority: 'urgent' })])

    expect(groups.map((g) => g.key)).toEqual(['urgent'])
  })

  it('excludes bought items', () => {
    const groups = groupOpenItems([item({ is_purchased: true })])

    expect(groups).toEqual([])
  })

  it('keeps an unrecognised priority in its own group, rather than dropping it (H04)', () => {
    const groups = groupOpenItems([item({ priority: 'asap' })])

    expect(groups).toHaveLength(1)
    expect(groups[0]).toMatchObject({ key: 'other', label: 'Other' })
    expect(groups[0].items[0].priority).toBe('asap')
  })
})

describe('boughtItems', () => {
  it('returns only purchased items, newest first', () => {
    const older = item({ id: 'a', is_purchased: true, purchased_at: '2026-10-01T08:00:00Z' })
    const newer = item({ id: 'b', is_purchased: true, purchased_at: '2026-10-01T09:00:00Z' })
    const open = item({ id: 'c', is_purchased: false })

    expect(boughtItems([older, open, newer])).toEqual([newer, older])
  })

  it('is empty when nothing is bought', () => {
    expect(boughtItems([item({ is_purchased: false })])).toEqual([])
  })
})
