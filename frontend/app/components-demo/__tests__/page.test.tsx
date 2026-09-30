/**
 * The UI kit demo page: its own Dark Mode toggle must not outlive the page (review, round
 * 2026-09-30-1). It used to strip `.light`/`.dark` on mount and never restore either on
 * unmount, so a cook who had chosen Dark saw the device theme after visiting this page,
 * until a reload.
 */

import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { ToastProvider } from '@/components/ui/Toast'
import { THEME_KEY } from '@/lib/theme'
import ComponentsDemo from '../page'

function renderDemo() {
  return render(
    <ToastProvider>
      <ComponentsDemo />
    </ToastProvider>
  )
}

beforeEach(() => {
  document.documentElement.classList.remove('dark', 'light')
  window.localStorage.clear()
})

describe('ComponentsDemo', () => {
  it('starts from whatever is already on <html>, instead of always stripping dark on mount', () => {
    document.documentElement.classList.add('dark')

    renderDemo()

    expect(document.documentElement).toHaveClass('dark')
  })

  it('restores the cook\'s own theme on the way out, not the device theme', () => {
    window.localStorage.setItem(THEME_KEY, 'dark')
    document.documentElement.classList.add('dark') // as the real app already applied it

    const { unmount } = renderDemo()
    expect(document.documentElement).toHaveClass('dark')

    fireEvent.click(screen.getByRole('button', { name: /Light Mode/ }))
    expect(document.documentElement).not.toHaveClass('dark')

    unmount()

    expect(document.documentElement).toHaveClass('dark')
  })
})
