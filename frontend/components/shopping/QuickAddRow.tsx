'use client'

/**
 * QuickAddRow: name first, with amount and unit optional. Left blank, the item still has to
 * satisfy the API (`quantity` and `unit` are both required, DEC-2), so a blank amount defaults
 * to 1 and a blank unit to `pcs` - "optional" for the cook, not for the request.
 *
 * F1: `onAdd` gets a fresh Idempotency-Key the first time a set of fields is submitted, and the
 * same key again if the fields are unchanged on a later submit - a retry of that action, not a
 * new one, which is what lets a lost response plus a resubmit replay instead of adding the item
 * twice. The row only clears on success; a failed attempt leaves the fields (and the key) in
 * place so the next "Add" click is that retry.
 */

import React, { useRef, useState } from 'react'
import Button from '@/components/ui/Button'
import { fieldErrorClass, fieldInputClass } from '@/components/ui/formStyles'
import { newIdempotencyKey } from '@/lib/api/shopping'
import type { ShoppingListItemCreate, ShoppingUnit } from '@/types/shopping'

export const UNITS: readonly ShoppingUnit[] = ['dl', 'tsp', 'tbsp', 'g', 'pcs']

export interface QuickAddRowProps {
  onAdd: (data: ShoppingListItemCreate, idempotencyKey: string) => Promise<unknown>
  pending?: boolean
}

/** The key minted for the fields last submitted, so an unchanged resubmit can reuse it. */
interface PendingAttempt {
  key: string
  fields: string
}

export function QuickAddRow({ onAdd, pending = false }: QuickAddRowProps) {
  const [name, setName] = useState('')
  const [amount, setAmount] = useState('')
  const [unit, setUnit] = useState<ShoppingUnit | ''>('')
  const attempt = useRef<PendingAttempt | null>(null)

  const trimmedName = name.trim()
  const trimmedAmount = amount.trim()
  // Blank is fine (it defaults to 1 below); anything else has to be a positive number (F4).
  const amountInvalid = trimmedAmount !== '' && !(Number(trimmedAmount) > 0)
  const canSubmit = trimmedName !== '' && !pending && !amountInvalid

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!canSubmit) return

    const quantity = trimmedAmount ? Number(trimmedAmount) : 1
    const fields = JSON.stringify({ name: trimmedName, amount: trimmedAmount, unit })
    const idempotencyKey =
      attempt.current && attempt.current.fields === fields
        ? attempt.current.key
        : newIdempotencyKey()
    attempt.current = { key: idempotencyKey, fields }

    try {
      await onAdd({ name: trimmedName, quantity, unit: unit || 'pcs' }, idempotencyKey)
      // Only a success clears the row and forgets the key; a failure keeps both so the next
      // "Add" on unchanged fields is a retry of this same action, not a new one.
      setName('')
      setAmount('')
      setUnit('')
      attempt.current = null
    } catch {
      // The caller already reported the error (a toast, typically); nothing further to do here.
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-wrap items-start gap-2" aria-label="Add an item">
      <input
        type="text"
        value={name}
        onChange={(event) => setName(event.target.value)}
        placeholder="Add an item"
        aria-label="Item name"
        className={`${fieldInputClass} min-w-[8rem] flex-1`}
      />
      <div>
        <input
          type="number"
          inputMode="decimal"
          min="0"
          step="any"
          value={amount}
          onChange={(event) => setAmount(event.target.value)}
          placeholder="Amount"
          aria-label="Amount"
          aria-invalid={amountInvalid}
          aria-describedby={amountInvalid ? 'quick-add-amount-error' : undefined}
          className={`${fieldInputClass} w-24`}
        />
        {amountInvalid && (
          <p id="quick-add-amount-error" className={fieldErrorClass}>
            Enter a number greater than 0
          </p>
        )}
      </div>
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
      <Button type="submit" size="md" disabled={!canSubmit} loading={pending}>
        Add
      </Button>
    </form>
  )
}

export default QuickAddRow
