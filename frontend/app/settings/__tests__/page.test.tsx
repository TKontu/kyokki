/**
 * Settings (Q33), reached from the app bar's "⋯". Its first setting is the theme (Q31).
 */

import React from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { THEME_KEY } from '@/lib/theme'
import SettingsPage from '../page'

const root = () => document.documentElement

beforeEach(() => {
  window.localStorage.clear()
  root().classList.remove('light', 'dark')
})

describe('Settings page', () => {
  it('has a heading and a Theme choice of System, Light and Dark', () => {
    render(<SettingsPage />)

    expect(screen.getByRole('heading', { level: 1, name: 'Settings' })).toBeInTheDocument()
    const group = screen.getByRole('radiogroup', { name: 'Theme' })
    expect(group).toBeInTheDocument()
    for (const name of ['System', 'Light', 'Dark']) {
      expect(screen.getByRole('radio', { name: new RegExp(`^${name}`) })).toBeInTheDocument()
    }
    expect(screen.getByRole('radio', { name: /^System/ })).toBeChecked()
  })

  it('switches to dark, keeps it on this device, and back to System', async () => {
    const user = userEvent.setup()
    render(<SettingsPage />)

    await user.click(screen.getByRole('radio', { name: /^Dark/ }))
    expect(root()).toHaveClass('dark')
    expect(window.localStorage.getItem(THEME_KEY)).toBe('dark')
    expect(screen.getByRole('radio', { name: /^Dark/ })).toBeChecked()

    await user.click(screen.getByRole('radio', { name: /^Light/ }))
    expect(root()).toHaveClass('light')
    expect(root()).not.toHaveClass('dark')

    await user.click(screen.getByRole('radio', { name: /^System/ }))
    expect(root()).not.toHaveClass('light')
    expect(root()).not.toHaveClass('dark')
    expect(window.localStorage.getItem(THEME_KEY)).toBeNull()
  })

  it('shows the stored choice when opened again', () => {
    window.localStorage.setItem(THEME_KEY, 'light')
    render(<SettingsPage />)

    expect(screen.getByRole('radio', { name: /^Light/ })).toBeChecked()
  })

  it('gives each option a full touch target', () => {
    render(<SettingsPage />)

    for (const radio of screen.getAllByRole('radio')) {
      expect(radio.closest('label')?.className).toMatch(/min-h-touch/)
    }
  })
})
