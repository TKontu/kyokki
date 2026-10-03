/**
 * ProductSearch: find an existing product by name, or say it is a new one (H15).
 */

import React from 'react'
import { render, screen } from '@testing-library/react'
import { ProductSearch } from '../ProductSearch'
import type { Category } from '@/types/category'
import type { ProductMaster } from '@/types/product'

jest.mock('@/hooks/useProducts')
import { useProductSearch } from '@/hooks/useProducts'
const mockUseProductSearch = useProductSearch as jest.Mock

const MILK: ProductMaster = {
  id: 'prod-milk',
  canonical_name: 'Milk',
  category: 'dairy',
  storage_type: 'refrigerator',
  default_shelf_life_days: 10,
  opened_shelf_life_days: null,
  frozen_shelf_life_days: null,
  avg_piece_grams: null,
  pack_grams: null,
  shelf_life_source: 'category',
  unit_type: 'volume',
  default_unit: 'dl',
  default_quantity: 10,
  min_stock_quantity: null,
  reorder_quantity: null,
  off_product_id: null,
  off_data: null,
  created_at: '2026-09-01T10:00:00Z',
  updated_at: '2026-09-01T10:00:00Z',
}

const CATEGORIES: Category[] = [
  {
    id: 'dairy',
    display_name: 'Dairy & Eggs',
    icon: '🥛',
    default_shelf_life_days: 7,
    frozen_shelf_life_days: null,
    sort_order: 20,
    default_storage: 'refrigerator',
    shelf_life_min_days: 1,
    shelf_life_max_days: 60,
  },
]

function renderSearch(product: ProductMaster, term = 'mil') {
  mockUseProductSearch.mockReturnValue({
    data: [product],
    settled: true,
    isFetching: false,
    isPlaceholderData: false,
    isPending: false,
  })
  return render(
    <ProductSearch
      categories={CATEGORIES}
      onPickExisting={jest.fn()}
      onPickNew={jest.fn()}
      term={term}
      onTermChange={jest.fn()}
    />
  )
}

beforeEach(() => {
  window.localStorage.clear()
})

describe('ProductSearch', () => {
  it('lists a found product by its English name by default', () => {
    renderSearch(MILK)

    expect(screen.getByRole('button', { name: 'Milk' })).toBeInTheDocument()
  })

  describe('display language (Post-MVP frontier item 13)', () => {
    it('lists the Finnish name once the cook has chosen Suomi', () => {
      window.localStorage.setItem('kyokki.language', 'fi')
      renderSearch({ ...MILK, display_names: { fi: 'Maito' } })

      expect(screen.getByRole('button', { name: 'Maito' })).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Milk' })).not.toBeInTheDocument()
    })

    it('falls back to English when there is no Finnish name', () => {
      window.localStorage.setItem('kyokki.language', 'fi')
      renderSearch(MILK)

      expect(screen.getByRole('button', { name: 'Milk' })).toBeInTheDocument()
    })
  })

  describe('chrome in Finnish (Post-MVP frontier item 13, phase 3)', () => {
    beforeEach(() => {
      window.localStorage.setItem('kyokki.language', 'fi')
    })

    it('labels the field in Finnish', () => {
      renderSearch(MILK)
      expect(screen.getByLabelText('Tuote')).toBeInTheDocument()
    })

    it('offers the default "new" wording in Finnish when the caller gives none', () => {
      mockUseProductSearch.mockReturnValue({
        data: [],
        settled: true,
        isFetching: false,
        isPlaceholderData: false,
        isPending: false,
      })
      render(
        <ProductSearch
          categories={CATEGORIES}
          onPickExisting={jest.fn()}
          onPickNew={jest.fn()}
          term="Barista oat"
          onTermChange={jest.fn()}
        />
      )
      expect(
        screen.getByRole('button', { name: 'Luo uusi: Barista oat' })
      ).toBeInTheDocument()
    })

    it('uses the default Finnish placeholder when the caller gives none', () => {
      mockUseProductSearch.mockReturnValue({
        data: [],
        settled: false,
        isFetching: false,
        isPlaceholderData: false,
        isPending: false,
      })
      render(
        <ProductSearch
          categories={CATEGORIES}
          onPickExisting={jest.fn()}
          onPickNew={jest.fn()}
          term=""
          onTermChange={jest.fn()}
        />
      )
      expect(screen.getByPlaceholderText('Maito, jauheliha, omenat…')).toBeInTheDocument()
    })

    it('still honours a caller-supplied label and placeholder', () => {
      mockUseProductSearch.mockReturnValue({
        data: [],
        settled: true,
        isFetching: false,
        isPlaceholderData: false,
        isPending: false,
      })
      render(
        <ProductSearch
          categories={CATEGORIES}
          onPickExisting={jest.fn()}
          onPickNew={jest.fn()}
          term="Barista oat"
          onTermChange={jest.fn()}
          newLabel={(term) => `New product: ${term}`}
        />
      )
      expect(
        screen.getByRole('button', { name: 'New product: Barista oat' })
      ).toBeInTheDocument()
    })
  })
})
