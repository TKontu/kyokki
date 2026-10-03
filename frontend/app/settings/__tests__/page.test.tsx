/**
 * Settings (Q33), reached from the app bar's "⋯". Its first setting is the theme (Q31).
 *
 * Icon curation (operator ask 2026-10-03) adds "Canonical icons", gated behind
 * `GET /api/icon-library/status`'s `curation_enabled` - every test here gets a default
 * handler answering false (off), same as the server's own default, unless a test says
 * otherwise.
 */

import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { LANGUAGE_KEY } from '@/lib/language'
import { THEME_KEY } from '@/lib/theme'
import SettingsPage from '../page'

const root = () => document.documentElement

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
beforeEach(() => {
  window.localStorage.clear()
  root().classList.remove('light', 'dark')
  server.use(
    http.get(`${API_URL}/icon-library/status`, () =>
      HttpResponse.json({ curation_enabled: false, library_count: 0, marked_count: 0 })
    )
  )
})
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <SettingsPage />
    </QueryClientProvider>
  )
}

describe('Settings page', () => {
  describe('display language (Post-MVP frontier item 13)', () => {
    it('offers English and Suomi, English checked by default', () => {
      renderPage()

      const group = screen.getByRole('radiogroup', { name: 'Display language' })
      expect(group).toBeInTheDocument()
      expect(screen.getByRole('radio', { name: /^English/ })).toBeChecked()
      expect(screen.getByRole('radio', { name: /^Suomi/ })).toBeInTheDocument()
    })

    it('switches to Suomi and keeps it on this device', async () => {
      const user = userEvent.setup()
      renderPage()

      await user.click(screen.getByRole('radio', { name: /^Suomi/ }))

      expect(window.localStorage.getItem(LANGUAGE_KEY)).toBe('fi')
      expect(screen.getByRole('radio', { name: /^Suomi/ })).toBeChecked()

      await user.click(screen.getByRole('radio', { name: /^English/ }))
      expect(window.localStorage.getItem(LANGUAGE_KEY)).toBeNull()
    })

    it('shows the stored choice when opened again', () => {
      window.localStorage.setItem(LANGUAGE_KEY, 'fi')
      renderPage()

      expect(screen.getByRole('radio', { name: /^Suomi/ })).toBeChecked()
    })
  })

  describe('display language (Post-MVP frontier item 13, phase 2: the screen\'s own text)', () => {
    afterEach(() => window.localStorage.clear())

    it('reads its own headings in Finnish once Suomi is chosen', () => {
      window.localStorage.setItem(LANGUAGE_KEY, 'fi')
      renderPage()

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
    renderPage()

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
    renderPage()

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
    renderPage()

    expect(screen.getByRole('radio', { name: /^Light/ })).toBeChecked()
  })

  it('gives each option a full touch target', () => {
    renderPage()

    for (const radio of screen.getAllByRole('radio')) {
      expect(radio.closest('label')?.className).toMatch(/min-h-touch/)
    }
  })
})

// Icon curation (operator ask 2026-10-03): the cook marks a good generated icon canonical
// on the product sheet; this section lists and downloads what has been marked.
describe('Settings page canonical icons', () => {
  function mockEnabled(marks: Array<Record<string, unknown>> = []) {
    server.use(
      http.get(`${API_URL}/icon-library/status`, () =>
        HttpResponse.json({ curation_enabled: true, library_count: 0, marked_count: marks.length })
      ),
      http.get(`${API_URL}/icon-library/marks`, () => HttpResponse.json(marks))
    )
  }

  it('is hidden when curation is disabled (the default)', () => {
    renderPage()

    expect(screen.queryByText('Canonical icons')).toBeNull()
  })

  it('shows the empty state when nothing is marked', async () => {
    mockEnabled([])
    renderPage()

    expect(await screen.findByText('Canonical icons')).toBeInTheDocument()
    expect(await screen.findByText('No icons marked yet')).toBeInTheDocument()
  })

  it('lists a marked icon with its name and an Unmark button', async () => {
    mockEnabled([
      { id: 'p-1', name: 'Quark', icon_version: 1790000000, marked_at: '2026-10-03T00:00:00Z' },
    ])
    renderPage()

    expect(await screen.findByText('Quark')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Unmark' })).toBeInTheDocument()
    expect(screen.getByText('1 icon marked')).toBeInTheDocument()
  })

  it('unmarks on click', async () => {
    mockEnabled([
      { id: 'p-1', name: 'Quark', icon_version: 1790000000, marked_at: '2026-10-03T00:00:00Z' },
    ])
    let unmarked = false
    server.use(
      http.delete(`${API_URL}/icon-library/marks/p-1`, () => {
        unmarked = true
        return HttpResponse.json({
          id: 'p-1',
          name: 'Quark',
          icon_version: 1790000000,
          marked_at: null,
        })
      })
    )
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: 'Unmark' }))

    await waitFor(() => expect(unmarked).toBe(true))
  })

  it('offers a Download bundle link to the bundle endpoint', async () => {
    mockEnabled([])
    renderPage()

    const link = await screen.findByRole('link', { name: 'Download bundle' })
    expect(link).toHaveAttribute('href', `${API_URL}/icon-library/bundle.zip`)
  })
})
