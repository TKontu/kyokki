/**
 * The fridge design mocks (Q17-M), for the operator to pick one to replace FridgeView on `/`.
 * Each takes the stock as a prop, so the demo page can feed it live stock or sample stock.
 */

import { Cielo } from './Cielo'
import { Crema } from './Crema'
import { Rosso } from './Rosso'
import type { FridgeMock } from './shared'

export const FRIDGE_MOCKS: FridgeMock[] = [
  {
    id: 'crema',
    name: 'Crema',
    description: 'Cream retro, freezer on top',
    Component: Crema,
  },
  {
    id: 'cielo',
    name: 'Cielo',
    description: 'Pastel blue, freezer drawer',
    Component: Cielo,
  },
  {
    id: 'rosso',
    name: 'Rosso',
    description: 'Red side-by-side, open shelves',
    Component: Rosso,
  },
]

export { fixtureItems } from './fixtures'
export type { FridgeMock, FridgeMockProps } from './shared'
