/**
 * The web app manifest (MVP-P2). Add to Home Screen on the iPad reads this, so the fields
 * that decide whether it launches as an app rather than a bookmark are worth pinning down.
 */

import manifest from '../manifest'
import { BRAND_COLOR, BRAND_NAME } from '@/lib/brand'

describe('manifest', () => {
  const m = manifest()

  it('launches as an app, not a browser tab', () => {
    expect(m.display).toBe('standalone')
    expect(m.start_url).toBe('/')
    expect(m.scope).toBe('/')
  })

  it('is named for the Home Screen', () => {
    expect(m.name).toBe(BRAND_NAME)
    expect(m.short_name).toBe(BRAND_NAME)
  })

  it('asks for portrait, which is how the iPad is mounted (Q17)', () => {
    // iOS ignores this for home-screen web apps; Android and Chrome honour it
    expect(m.orientation).toBe('portrait')
  })

  it('carries both icon sizes as real PNGs', () => {
    const icons = m.icons ?? []
    expect(icons.map((i) => i.sizes)).toEqual(['192x192', '512x512'])
    expect(icons.every((i) => i.type === 'image/png')).toBe(true)
    expect(icons.map((i) => i.src)).toEqual([
      '/icons/icon-192.png',
      '/icons/icon-512.png',
    ])
  })

  it('matches the colours the app itself uses', () => {
    expect(m.theme_color).toBe(BRAND_COLOR)
    expect(m.background_color).toBe('#ffffff')
  })
})
