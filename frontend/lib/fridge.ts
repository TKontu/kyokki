/**
 * The fridge's areas (V3, operator ask 2026-09-24).
 *
 * The stock screen is drawn as a fridge: an area per kind of food, plus the freezer and the
 * pantry as compartments of their own, and a shelf across the top for what is going stale.
 * Categories map to areas here and only here; the backend's seeded ids are in
 * `backend/app/db/seed_categories.py`, and the test pins that every one has an area.
 */

import { calculateDaysUntilExpiry } from '@/lib/dates'
import { stalenessOf } from '@/lib/staleness'
import { compareStock, isInactive } from '@/lib/stock'
import type { InventoryItem } from '@/types/inventory'

export type AreaId =
  | 'meat'
  | 'veggies'
  | 'fruits'
  | 'dairy'
  | 'bread'
  | 'ready_meals'
  | 'drinks'
  | 'pantry'
  | 'freezer'
  | 'other'

export interface Area {
  id: AreaId
  label: string
  icon: string
  /** Where it is drawn: inside the fridge body, or a compartment of its own below it. */
  compartment: 'fridge' | 'freezer' | 'pantry' | 'other'
  categories: string[]
}

export const AREAS: Area[] = [
  { id: 'meat', label: 'Meat & fish', icon: '🥩', compartment: 'fridge', categories: ['meat', 'fish'] },
  { id: 'veggies', label: 'Veggies', icon: '🥕', compartment: 'fridge', categories: ['produce'] },
  { id: 'fruits', label: 'Fruits', icon: '🍎', compartment: 'fridge', categories: ['fruits'] },
  { id: 'dairy', label: 'Dairy', icon: '🥛', compartment: 'fridge', categories: ['dairy', 'cheese'] },
  { id: 'bread', label: 'Bread', icon: '🍞', compartment: 'fridge', categories: ['bread'] },
  { id: 'ready_meals', label: 'Ready meals', icon: '🍲', compartment: 'fridge', categories: ['ready_meals'] },
  { id: 'drinks', label: 'Drinks', icon: '🧃', compartment: 'fridge', categories: ['beverages'] },
  {
    id: 'pantry',
    label: 'Pantry',
    icon: '🥫',
    compartment: 'pantry',
    categories: ['pantry', 'condiments', 'snacks'],
  },
  { id: 'freezer', label: 'Freezer', icon: '🧊', compartment: 'freezer', categories: ['frozen'] },
  { id: 'other', label: 'Other', icon: '📦', compartment: 'other', categories: [] },
]

const BY_CATEGORY = new Map(
  AREAS.flatMap((area) => area.categories.map((category) => [category, area.id] as const))
)

/** Where an item is drawn. The freezer wins over the category: frozen mince is in the freezer. */
export function areaOf(item: Pick<InventoryItem, 'category' | 'location'>): AreaId {
  if (item.location === 'freezer') return 'freezer'
  return BY_CATEGORY.get(item.category) ?? 'other'
}

export interface FridgeView {
  /** Red and orange tiles, stalest first: the shelf across the top. */
  goingStale: InventoryItem[]
  /** Past their date - what the shelf's clear link offers to throw away. */
  expired: InventoryItem[]
  /** Every area in fridge order, empty ones included so the fridge keeps its shape. */
  areas: { area: Area; items: InventoryItem[] }[]
}

export function buildFridgeView(items: InventoryItem[]): FridgeView {
  const here = items.filter((item) => !isInactive(item)).sort(compareStock)
  const byArea = new Map<AreaId, InventoryItem[]>()
  for (const item of here) {
    const id = areaOf(item)
    byArea.set(id, [...(byArea.get(id) ?? []), item])
  }
  return {
    goingStale: here.filter((item) => {
      const tier = stalenessOf(item)
      return tier === 'stale' || tier === 'soon'
    }),
    expired: here.filter((item) => calculateDaysUntilExpiry(item.expiry_date) < 0),
    areas: AREAS.map((area) => ({ area, items: byArea.get(area.id) ?? [] })),
  }
}

/**
 * An area's grid (V4): what is here, stalest first, then what was used up - latest first - as
 * grey tiles a tap brings back. Nothing thrown away: that is the Gone screen's.
 */
export function areaTiles(items: InventoryItem[], areaId: AreaId): InventoryItem[] {
  const inArea = items.filter((item) => areaOf(item) === areaId)
  const here = inArea.filter((item) => !isInactive(item)).sort(compareStock)
  const usedUp = inArea
    .filter((item) => item.status === 'empty')
    .sort((a, b) => (b.consumed_at ?? '').localeCompare(a.consumed_at ?? ''))
  return [...here, ...usedUp]
}
