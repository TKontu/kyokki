/**
 * A crowded fridge: every area a handful over what its region can show, and more going
 * stale than the strip has room for. For tests, and for the screenshots the operator judges.
 */

import type { InventoryItem } from '@/types/inventory'
import { CIELO_BOX } from '../CieloFridge'
import { dotCapacity } from '../capacity'
import { inDays, item, many, stale } from './stock'

export function crowdedItems(): InventoryItem[] {
  const over = (id: keyof typeof CIELO_BOX) => dotCapacity(CIELO_BOX[id]) + 5
  return [
    // A long one-word Finnish name, to show it keeps inside its tile (review F1)
    item({
      id: 'stale-long-name',
      product_name: 'Laktoositonkermaviili',
      category: 'dairy',
      category_icon: '🥛',
      expiry_date: inDays(0),
    }),
    ...stale(14),
    ...many(over('meat'), { category: 'meat', category_icon: '🥩' }),
    ...many(over('veggies'), { category: 'produce', category_icon: '🥬' }),
    ...many(over('fruits'), { category: 'fruits', category_icon: '🍎' }),
    ...many(over('dairy'), { category: 'dairy', category_icon: '🥛' }),
    ...many(over('bread'), { category: 'bread', category_icon: '🍞' }),
    ...many(over('ready_meals'), { category: 'ready_meals', category_icon: '🍲' }),
    ...many(over('drinks'), { category: 'beverages', category_icon: '🥤' }),
    ...many(over('pantry'), { category: 'pantry', category_icon: '🥫' }),
    ...many(over('freezer'), { category: 'frozen', category_icon: '🧊', location: 'freezer' }),
    ...many(over('other'), { category: 'household', category_icon: '🧽' }),
  ]
}
