import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { QuickAddRow } from '../QuickAddRow'

describe('QuickAddRow', () => {
  it('adds by name alone, defaulting amount to 1 and unit to pcs', () => {
    const onAdd = jest.fn()
    render(<QuickAddRow onAdd={onAdd} />)

    fireEvent.change(screen.getByLabelText('Item name'), { target: { value: 'Bananas' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))

    expect(onAdd).toHaveBeenCalledWith({ name: 'Bananas', quantity: 1, unit: 'pcs' })
  })

  it('sends the amount and unit when given', () => {
    const onAdd = jest.fn()
    render(<QuickAddRow onAdd={onAdd} />)

    fireEvent.change(screen.getByLabelText('Item name'), { target: { value: 'Milk' } })
    fireEvent.change(screen.getByLabelText('Amount'), { target: { value: '2' } })
    fireEvent.change(screen.getByLabelText('Unit'), { target: { value: 'dl' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))

    expect(onAdd).toHaveBeenCalledWith({ name: 'Milk', quantity: 2, unit: 'dl' })
  })

  it('clears the row after adding', () => {
    const onAdd = jest.fn()
    render(<QuickAddRow onAdd={onAdd} />)

    const nameField = screen.getByLabelText('Item name') as HTMLInputElement
    fireEvent.change(nameField, { target: { value: 'Bananas' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))

    expect(nameField.value).toBe('')
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
})
