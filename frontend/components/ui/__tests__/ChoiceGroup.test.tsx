import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { ChoiceGroup } from '../ChoiceGroup'

const OPTIONS = [
  { value: 'main_fridge', label: 'Fridge' },
  { value: 'freezer', label: 'Freezer' },
]

describe('ChoiceGroup', () => {
  it('renders a named radio group with the selected option checked', () => {
    render(<ChoiceGroup label="Location" name="loc" options={OPTIONS} value="freezer" onChange={jest.fn()} />)

    expect(screen.getByRole('radiogroup', { name: 'Location' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Freezer' })).toBeChecked()
    expect(screen.getByRole('radio', { name: 'Fridge' })).not.toBeChecked()
  })

  it('reports the chosen value', () => {
    const onChange = jest.fn()
    render(<ChoiceGroup label="Location" name="loc" options={OPTIONS} value="freezer" onChange={onChange} />)

    fireEvent.click(screen.getByText('Fridge'))

    expect(onChange).toHaveBeenCalledWith('main_fridge')
  })

  it('keeps each hidden input inside its label', () => {
    render(<ChoiceGroup label="Location" name="loc" options={OPTIONS} value={null} onChange={jest.fn()} />)

    const label = screen.getByRole('radio', { name: 'Fridge' }).closest('label')
    expect(label?.className).toContain('relative')
  })
})
