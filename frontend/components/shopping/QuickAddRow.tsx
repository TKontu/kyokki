'use client'

/**
 * QuickAddRow: name first, with amount and unit optional. Left blank, the item still has to
 * satisfy the API (`quantity` and `unit` are both required, DEC-2), so a blank amount defaults
 * to 1 and a blank unit to `pcs` - "optional" for the cook, not for the request.
 */

import React, { useState } from 'react'
import Button from '@/components/ui/Button'
import { fieldInputClass } from '@/components/ui/formStyles'
import type { ShoppingListItemCreate, ShoppingUnit } from '@/types/shopping'

export const UNITS: readonly ShoppingUnit[] = ['dl', 'tsp', 'tbsp', 'g', 'pcs']

export interface QuickAddRowProps {
  onAdd: (data: ShoppingListItemCreate) => void
  pending?: boolean
}

export function QuickAddRow({ onAdd, pending = false }: QuickAddRowProps) {
  const [name, setName] = useState('')
  const [amount, setAmount] = useState('')
  const [unit, setUnit] = useState<ShoppingUnit | ''>('')

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    const trimmed = name.trim()
    if (!trimmed || pending) return

    const quantity = amount.trim() ? Number(amount) : 1
    if (!Number.isFinite(quantity) || quantity <= 0) return

    onAdd({ name: trimmed, quantity, unit: unit || 'pcs' })
    setName('')
    setAmount('')
    setUnit('')
  }

  return (
    <form onSubmit={submit} className="flex flex-wrap items-center gap-2" aria-label="Add an item">
      <input
        type="text"
        value={name}
        onChange={(event) => setName(event.target.value)}
        placeholder="Add an item"
        aria-label="Item name"
        className={`${fieldInputClass} min-w-[8rem] flex-1`}
      />
      <input
        type="number"
        inputMode="decimal"
        min="0"
        step="any"
        value={amount}
        onChange={(event) => setAmount(event.target.value)}
        placeholder="Amount"
        aria-label="Amount"
        className={`${fieldInputClass} w-24`}
      />
      <select
        value={unit}
        onChange={(event) => setUnit(event.target.value as ShoppingUnit)}
        aria-label="Unit"
        className={`${fieldInputClass} w-24`}
      >
        <option value="">pcs</option>
        {UNITS.map((each) => (
          <option key={each} value={each}>
            {each}
          </option>
        ))}
      </select>
      <Button type="submit" size="md" disabled={!name.trim() || pending} loading={pending}>
        Add
      </Button>
    </form>
  )
}

export default QuickAddRow
