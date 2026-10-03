import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QuickAddRow } from '../QuickAddRow'
import { LANGUAGE_KEY } from '@/lib/language'

function uuid(key: string) {
  expect(key).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i)
}

describe('QuickAddRow', () => {
  it('adds by name alone, defaulting amount to 1 and unit to pcs, with a fresh Idempotency-Key', async () => {
    const onAdd = jest.fn().mockResolvedValue(undefined)
    render(<QuickAddRow onAdd={onAdd} />)

    fireEvent.change(screen.getByLabelText('Item name'), { target: { value: 'Bananas' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))

    await waitFor(() => expect(onAdd).toHaveBeenCalled())
    const [data, key] = onAdd.mock.calls[0]
    expect(data).toEqual({ name: 'Bananas', quantity: 1, unit: 'pcs' })
    uuid(key)
  })

  it('sends the amount and unit when given', async () => {
    const onAdd = jest.fn().mockResolvedValue(undefined)
    render(<QuickAddRow onAdd={onAdd} />)

    fireEvent.change(screen.getByLabelText('Item name'), { target: { value: 'Milk' } })
    fireEvent.change(screen.getByLabelText('Amount'), { target: { value: '2' } })
    fireEvent.change(screen.getByLabelText('Unit'), { target: { value: 'dl' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))

    await waitFor(() => expect(onAdd).toHaveBeenCalled())
    expect(onAdd.mock.calls[0][0]).toEqual({ name: 'Milk', quantity: 2, unit: 'dl' })
  })

  it('clears the row only once adding succeeds', async () => {
    const onAdd = jest.fn().mockResolvedValue(undefined)
    render(<QuickAddRow onAdd={onAdd} />)

    const nameField = screen.getByLabelText('Item name') as HTMLInputElement
    fireEvent.change(nameField, { target: { value: 'Bananas' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))

    await waitFor(() => expect(nameField.value).toBe(''))
  })

  it('does nothing on an empty name', () => {
    const onAdd = jest.fn()
    render(<QuickAddRow onAdd={onAdd} />)

    expect(screen.getByRole('button', { name: 'Add' })).toBeDisabled()
  })

  it('disables Add while a request is pending', () => {
    render(<QuickAddRow onAdd={jest.fn()} pending />)

    expect(screen.getByRole('button', { name: 'Add' })).toBeDisabled()
  })

  describe('amount validation (F4)', () => {
    it('marks the amount invalid and disables Add for a zero or negative amount', () => {
      render(<QuickAddRow onAdd={jest.fn()} />)

      fireEvent.change(screen.getByLabelText('Item name'), { target: { value: 'Bananas' } })
      fireEvent.change(screen.getByLabelText('Amount'), { target: { value: '0' } })

      const amountField = screen.getByLabelText('Amount')
      expect(amountField).toHaveAttribute('aria-invalid', 'true')
      expect(screen.getByText(/enter a number greater than 0/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Add' })).toBeDisabled()
    })

    it('marks the amount invalid for a negative number', () => {
      render(<QuickAddRow onAdd={jest.fn()} />)

      fireEvent.change(screen.getByLabelText('Item name'), { target: { value: 'Bananas' } })
      fireEvent.change(screen.getByLabelText('Amount'), { target: { value: '-2' } })

      expect(screen.getByLabelText('Amount')).toHaveAttribute('aria-invalid', 'true')
      expect(screen.getByRole('button', { name: 'Add' })).toBeDisabled()
    })

    it('is valid when the amount is left blank', () => {
      render(<QuickAddRow onAdd={jest.fn()} />)

      fireEvent.change(screen.getByLabelText('Item name'), { target: { value: 'Bananas' } })

      expect(screen.getByLabelText('Amount')).toHaveAttribute('aria-invalid', 'false')
      expect(screen.getByRole('button', { name: 'Add' })).not.toBeDisabled()
    })
  })

  describe('Idempotency-Key per action (F1)', () => {
    it('reuses the same key when retrying the same fields after a failure', async () => {
      const onAdd = jest.fn().mockRejectedValueOnce(new Error('network error'))
      onAdd.mockResolvedValueOnce(undefined)
      render(<QuickAddRow onAdd={onAdd} />)

      fireEvent.change(screen.getByLabelText('Item name'), { target: { value: 'Bananas' } })
      fireEvent.click(screen.getByRole('button', { name: 'Add' }))
      await waitFor(() => expect(onAdd).toHaveBeenCalledTimes(1))

      // The failed attempt's fields are still in the row (not cleared), so a resubmit here is a
      // retry of the same action - it must reuse the first key, not mint a new one.
      fireEvent.click(screen.getByRole('button', { name: 'Add' }))
      await waitFor(() => expect(onAdd).toHaveBeenCalledTimes(2))

      const [, firstKey] = onAdd.mock.calls[0]
      const [, secondKey] = onAdd.mock.calls[1]
      expect(secondKey).toBe(firstKey)
    })

    it('mints a new key for a different item', async () => {
      const onAdd = jest.fn().mockResolvedValue(undefined)
      render(<QuickAddRow onAdd={onAdd} />)

      fireEvent.change(screen.getByLabelText('Item name'), { target: { value: 'Bananas' } })
      fireEvent.click(screen.getByRole('button', { name: 'Add' }))
      await waitFor(() => expect(onAdd).toHaveBeenCalledTimes(1))

      fireEvent.change(screen.getByLabelText('Item name'), { target: { value: 'Milk' } })
      fireEvent.click(screen.getByRole('button', { name: 'Add' }))
      await waitFor(() => expect(onAdd).toHaveBeenCalledTimes(2))

      const [, firstKey] = onAdd.mock.calls[0]
      const [, secondKey] = onAdd.mock.calls[1]
      expect(secondKey).not.toBe(firstKey)
    })
  })

  describe('display language (Post-MVP frontier item 13, phase 2)', () => {
    afterEach(() => window.localStorage.clear())

    it('reads the row in Finnish once Suomi is chosen', () => {
      window.localStorage.setItem(LANGUAGE_KEY, 'fi')
      render(<QuickAddRow onAdd={jest.fn()} />)

      expect(screen.getByLabelText('Tuotteen nimi')).toBeInTheDocument()
      expect(screen.getByLabelText('Määrä')).toBeInTheDocument()
      expect(screen.getByLabelText('Yksikkö')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Lisää' })).toBeInTheDocument()
    })
  })
})
