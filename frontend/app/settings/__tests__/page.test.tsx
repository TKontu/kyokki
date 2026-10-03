/**
 * Settings (Q33), reached from the app bar's "⋯". Its first setting is the theme (Q31).
 */

import React from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LANGUAGE_KEY } from '@/lib/language'
import { THEME_KEY } from '@/lib/theme'
import SettingsPage from '../page'

const root = () => document.documentElement

beforeEach(() => {
  window.localStorage.clear()
  root().classList.remove('light', 'dark')
})

describe('Settings page', () => {
  describe('display language (Post-MVP frontier item 13)', () => {
    it('offers English and Suomi, English checked by default', () => {
      render(<SettingsPage />)

      const group = screen.getByRole('radiogroup', { name: 'Display language' })
      expect(group).toBeInTheDocument()
      expect(screen.getByRole('radio', { name: /^English/ })).toBeChecked()
      expect(screen.getByRole('radio', { name: /^Suomi/ })).toBeInTheDocument()
    })

    it('switches to Suomi and keeps it on this device', async () => {
      const user = userEvent.setup()
      render(<SettingsPage />)

      await user.click(screen.getByRole('radio', { name: /^Suomi/ }))

      expect(window.localStorage.getItem(LANGUAGE_KEY)).toBe('fi')
      expect(screen.getByRole('radio', { name: /^Suomi/ })).toBeChecked()

      await user.click(screen.getByRole('radio', { name: /^English/ }))
      expect(window.localStorage.getItem(LANGUAGE_KEY)).toBeNull()
    })

    it('shows the stored choice when opened again', () => {
      window.localStorage.setItem(LANGUAGE_KEY, 'fi')
      render(<SettingsPage />)

      expect(screen.getByRole('radio', { name: /^Suomi/ })).toBeChecked()
    })
  })

  describe('display language (Post-MVP frontier item 13, phase 2: the screen\'s own text)', () => {
    afterEach(() => window.localStorage.clear())

    it('reads its own headings in Finnish once Suomi is chosen', () => {
      window.localStorage.setItem(LANGUAGE_KEY, 'fi')
      render(<SettingsPage />)

      expect(screen.getByRole('heading', { level: 1, name: 'Asetukset' })).toBeInTheDocument()
      expect(screen.getByRole('radiogroup', { name: 'Näyttökieli' })).toBeInTheDocument()
      expect(screen.getByRole('radiogroup', { name: 'Teema' })).toBeInTheDocument()
      // "English" and "Suomi" are the language's own endonyms, unchanged by the choice
      expect(screen.getByRole('radio', { name: /^Suomi/ })).toBeInTheDocument()
      expect(screen.getByRole('radio', { name: /^English/ })).toBeInTheDocument()
      // The theme's own option names translate too
      expect(screen.getByRole('radio', { name: /^Järjestelmä/ })).toBeInTheDocument()
      expect(screen.getByRole('radio', { name: /^Vaalea/ })).toBeInTheDocument()
      expect(screen.getByRole('radio', { name: /^Tumma/ })).toBeInTheDocument()
    })
  })

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
