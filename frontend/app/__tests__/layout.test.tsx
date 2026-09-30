/**
 * The root layout's theme boot script (Q31): it has to be in `<head>`, before `<body>`, or a
 * dark kitchen flashes white before hydration. Nothing rendered `layout.tsx` at all before
 * this, so deleting the `<script>` (or the `suppressHydrationWarning` its class changes need)
 * failed nothing.
 */

import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { THEME_SCRIPT } from '@/lib/theme'
import RootLayout from '../layout'

jest.mock('next/navigation', () => ({ usePathname: () => '/' }))

function renderedHtml(): string {
  return renderToStaticMarkup(
    <RootLayout>
      <div>the page</div>
    </RootLayout>
  )
}

describe('RootLayout', () => {
  it('inlines the theme script in <head>, before <body>, so it runs before first paint', () => {
    const html = renderedHtml()

    expect(html).toContain(THEME_SCRIPT)
    const scriptAt = html.indexOf(THEME_SCRIPT)
    const bodyAt = html.indexOf('<body')
    expect(scriptAt).toBeGreaterThan(-1)
    expect(bodyAt).toBeGreaterThan(-1)
    expect(scriptAt).toBeLessThan(bodyAt)
  })

  it('renders the page it wraps', () => {
    expect(renderedHtml()).toContain('the page')
  })
})
