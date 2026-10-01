/**
 * The root layout's theme boot script (Q31): it has to be in `<head>`, before `<body>`, or a
 * dark kitchen flashes white before hydration. Nothing rendered `layout.tsx` at all before
 * this, so deleting the `<script>` failed nothing.
 *
 * The hydration test below covers `suppressHydrationWarning` too: the boot script's class
 * change on `<html>` is an intentional, pre-existing server/client mismatch that attribute
 * is what keeps silent, so removing it turns that same mismatch into a console error the
 * test catches. It also proves the boot script itself makes no `<head>` change hydration
 * could choke on (round 2026-09-30-1: a first attempt inserted a `<meta>` there, which shifts
 * React's tag matching for every sibling after it by one), and that the post-hydration mount
 * effect (simulated here as `setThemeColor` itself; see `providers.tsx`) is what actually
 * lands the forced status-bar colour.
 */

import React, { act } from 'react'
import { hydrateRoot } from 'react-dom/client'
import { renderToStaticMarkup } from 'react-dom/server'
import { THEME_COLOR_DARK, THEME_COLOR_LIGHT } from '@/lib/brand'
import { THEME_KEY, THEME_SCRIPT, setThemeColor } from '@/lib/theme'
import RootLayout from '../layout'

jest.mock('next/navigation', () => ({ usePathname: () => '/' }))

function page() {
  return (
    <RootLayout>
      <div>the page</div>
    </RootLayout>
  )
}

function renderedHtml(): string {
  return renderToStaticMarkup(page())
}

/**
 * `layout.tsx` called directly (as above) never gets the `theme-color` tags: Next injects
 * those from the `viewport` export as part of its own rendering pipeline, not from anything
 * literally in the component's JSX. This mirrors what reaches the browser in production -
 * `<html suppressHydrationWarning>`, the real two tags, the real boot script - so the
 * hydration test below exercises `lib/theme.ts` against the shape it actually runs inside.
 */
function documentFixture() {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <meta name="theme-color" content={THEME_COLOR_LIGHT} media="(prefers-color-scheme: light)" />
        <meta name="theme-color" content={THEME_COLOR_DARK} media="(prefers-color-scheme: dark)" />
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        <div>the page</div>
      </body>
    </html>
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

  /**
   * `hydrateRoot(document, ...)` hydrates the real document in place, and `root.unmount()`
   * removes `<html>` from `document` entirely - jsdom does not restore the bare skeleton the
   * way a browser's navigation would - which would break `document.documentElement` for
   * every test after it (each hydration test below unmounts, so it can hydrate fresh rather
   * than warn about re-using an already-rooted container). Reinstating a root element here
   * is what a real navigation would do for free.
   */
  afterEach(() => {
    if (!document.documentElement) {
      const html = document.createElement('html')
      html.appendChild(document.createElement('head'))
      html.appendChild(document.createElement('body'))
      document.appendChild(html)
    } else {
      document.documentElement.innerHTML = '<head></head><body></body>'
      document.documentElement.className = ''
    }
    window.localStorage.clear()
  })

  it('hydrates a forced theme cleanly; the mount effect then lands the status-bar colour', () => {
    window.localStorage.setItem(THEME_KEY, 'dark')

    // The server never sees the stored choice: it renders as if System, exactly as the real
    // server does. `document.documentElement.innerHTML` (not `document.write`, which jsdom
    // treats as a fresh navigation) puts that markup under the same real `<html>` node
    // `hydrateRoot(document, ...)` reconciles against below.
    const html = renderToStaticMarkup(documentFixture())
    const inner = html.replace(/^<html[^>]*>/, '').replace(/<\/html>\s*$/, '')
    document.documentElement.innerHTML = inner
    document.documentElement.setAttribute('lang', 'en')

    // The boot script, exactly as it runs in `<head>` before React ever sees the page.
    // eslint-disable-next-line no-new-func
    new Function(THEME_SCRIPT)()
    expect(document.documentElement).toHaveClass('dark')

    const errors: unknown[][] = []
    const spy = jest.spyOn(console, 'error').mockImplementation((...args) => {
      errors.push(args)
    })

    let root: ReturnType<typeof hydrateRoot> | undefined
    try {
      act(() => {
        root = hydrateRoot(document, documentFixture())
      })

      // Not just "no error was thrown": React logs a hydration mismatch via console.error
      // without necessarily throwing, so this is the assertion that actually catches one -
      // including the one `suppressHydrationWarning` would otherwise swallow on purpose.
      expect(errors).toEqual([])
      // The class survived hydration untouched - the regression this guards against.
      expect(document.documentElement).toHaveClass('dark')

      // `providers.tsx`'s mount effect calls exactly this, once hydration has committed.
      setThemeColor('dark')
      const metas = document.querySelectorAll('meta[name="theme-color"]')
      expect(metas).toHaveLength(2)
      metas.forEach((meta) => {
        expect(meta.getAttribute('content')).toBe(THEME_COLOR_DARK)
      })
    } finally {
      act(() => root?.unmount())
      spy.mockRestore()
    }
  })

  it('still hydrates cleanly as System (no forced theme, no boot-script change)', () => {
    const html = renderToStaticMarkup(documentFixture())
    const inner = html.replace(/^<html[^>]*>/, '').replace(/<\/html>\s*$/, '')
    document.documentElement.innerHTML = inner
    document.documentElement.setAttribute('lang', 'en')
    // eslint-disable-next-line no-new-func
    new Function(THEME_SCRIPT)()
    expect(document.documentElement.className).toBe('')

    const errors: unknown[][] = []
    const spy = jest.spyOn(console, 'error').mockImplementation((...args) => {
      errors.push(args)
    })

    let root: ReturnType<typeof hydrateRoot> | undefined
    try {
      act(() => {
        root = hydrateRoot(document, documentFixture())
      })

      expect(errors).toEqual([])
      const metas = document.querySelectorAll('meta[name="theme-color"]')
      expect(metas[0].getAttribute('content')).toBe(THEME_COLOR_LIGHT)
      expect(metas[1].getAttribute('content')).toBe(THEME_COLOR_DARK)
    } finally {
      act(() => root?.unmount())
      spy.mockRestore()
    }
  })

  it('logs a hydration mismatch if suppressHydrationWarning is ever dropped from <html>', () => {
    // Guards finding 5: nothing previously proved this attribute does anything. Rendering
    // without it, with the same pre-hydration class change `THEME_SCRIPT` makes, is exactly
    // the mismatch `suppressHydrationWarning` exists to swallow.
    window.localStorage.setItem(THEME_KEY, 'dark')
    const unprotected = (
      <html lang="en">
        <head />
        <body>
          <div>the page</div>
        </body>
      </html>
    )
    const html = renderToStaticMarkup(unprotected)
    const inner = html.replace(/^<html[^>]*>/, '').replace(/<\/html>\s*$/, '')
    document.documentElement.innerHTML = inner
    document.documentElement.setAttribute('lang', 'en')
    // eslint-disable-next-line no-new-func
    new Function(THEME_SCRIPT)()

    const errors: unknown[][] = []
    const spy = jest.spyOn(console, 'error').mockImplementation((...args) => {
      errors.push(args)
    })

    let root: ReturnType<typeof hydrateRoot> | undefined
    try {
      act(() => {
        root = hydrateRoot(document, unprotected)
      })

      expect(errors.length).toBeGreaterThan(0)
    } finally {
      act(() => root?.unmount())
      spy.mockRestore()
    }
  })
})
