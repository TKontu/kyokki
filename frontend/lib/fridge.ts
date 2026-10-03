/**
 * The fridge's areas (V3, operator ask 2026-09-24).
 *
 * The stock screen is drawn as a fridge: an area per kind of food, plus the freezer and the
 * larder (pantry, sauces, spices and bread) as compartments of their own, and a shelf across the top for what
 * is going stale.
 * Categories map to areas here and only here; the backend's seeded ids are in
 * `backend/app/db/seed_categories.py`, and the test pins that every one has an area.
 *
 * `AREAS[].label` stays English and unchanged (review F1, round 2026-10-03-1):
 * `app/area/[id]/page.tsx` (out of scope this phase) reads it directly, and the planner's
 * original spec never granted this file, so a Finnish screen still read "Meat & fish".
 * `areaLabel` is the language-aware way to read the same name - no hooks here, by design;
 * the caller (already holding `useLanguage()`) passes the language in, defaulting to `'en'`.
 */

import { calculateDaysUntilExpiry } from '@/lib/dates'
import type { Language } from '@/lib/language'
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
  | 'condiments'
  | 'spices'
  | 'freezer'
  | 'other'

export interface Area {
  id: AreaId
  label: string
  icon: string
  /**
   * Where it lives, for a reader: inside the fridge (body or door), the freezer drawer, the
   * larder beside the fridge (its shelves - pantry, sauces, spices - and the bread basket on
   * top), or Other's crate at the larder's foot. Descriptive only - nothing reads it; where an area is drawn is
   * `CIELO_BOX` in `components/fridge/CieloFridge.tsx`.
   */
  compartment: 'fridge' | 'freezer' | 'pantry' | 'other'
  categories: string[]
}

export const AREAS: Area[] = [
  { id: 'meat', label: 'Meat & fish', icon: '🥩', compartment: 'fridge', categories: ['meat', 'fish'] },
  { id: 'veggies', label: 'Veggies', icon: '🥕', compartment: 'fridge', categories: ['produce'] },
  { id: 'fruits', label: 'Fruits', icon: '🍎', compartment: 'fridge', categories: ['fruits'] },
  { id: 'dairy', label: 'Dairy', icon: '🥛', compartment: 'fridge', categories: ['dairy', 'cheese'] },
  // Bread lives in a basket by the larder (operator, 2026-09-26, Q23)
  { id: 'bread', label: 'Bread', icon: '🍞', compartment: 'pantry', categories: ['bread'] },
  { id: 'ready_meals', label: 'Ready meals', icon: '🍲', compartment: 'fridge', categories: ['ready_meals'] },
  { id: 'drinks', label: 'Drinks', icon: '🧃', compartment: 'fridge', categories: ['beverages'] },
  { id: 'pantry', label: 'Pantry', icon: '🥫', compartment: 'pantry', categories: ['pantry', 'snacks'] },
  // Sauces and spices each have a larder shelf of their own (operator, 2026-09-27, Q35, Q36)
  {
    id: 'condiments',
    label: 'Sauces & condiments',
    icon: '🍯',
    compartment: 'pantry',
    categories: ['condiments'],
  },
  { id: 'spices', label: 'Spices', icon: '🧂', compartment: 'pantry', categories: ['spices'] },
  { id: 'freezer', label: 'Freezer', icon: '🧊', compartment: 'freezer', categories: ['frozen'] },
  { id: 'other', label: 'Other', icon: '📦', compartment: 'other', categories: [] },
]

const AREA_LABELS_EN = Object.fromEntries(AREAS.map((area) => [area.id, area.label])) as Record<
  AreaId,
  string
>

const AREA_LABELS_FI: Record<AreaId, string> = {
  meat: 'Liha ja kala',
  veggies: 'Vihannekset',
  fruits: 'Hedelmät',
  dairy: 'Maitotuotteet',
  bread: 'Leipä',
  ready_meals: 'Valmisruoat',
  drinks: 'Juomat',
  pantry: 'Kuivamuona',
  condiments: 'Kastikkeet',
  spices: 'Mausteet',
  freezer: 'Pakastin',
  other: 'Muut',
}

/** An area's own name, in the chosen language - English (`AREAS[].label`) by default. */
export function areaLabel(id: AreaId, language: Language = 'en'): string {
  return language === 'fi' ? AREA_LABELS_FI[id] : AREA_LABELS_EN[id]
}

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
