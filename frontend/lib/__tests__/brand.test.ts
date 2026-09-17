/**
 * The brand constants feed both the manifest and the generated icons (MVP-P2), so the two
 * can never drift apart.
 */

import {
  APPLE_ICON_PATH,
  APPLE_ICON_SIZE,
  BACKGROUND_COLOR,
  BRAND_COLOR,
  BRAND_NAME,
  ICON_SIZES,
  THEME_COLOR_DARK,
  THEME_COLOR_LIGHT,
  iconPath,
} from '../brand'

describe('brand', () => {
  it('names the app the way the Home Screen should', () => {
    expect(BRAND_NAME).toBe('Kyokki')
  })

  it('uses colours from the Tailwind palette', () => {
    expect(BRAND_COLOR).toBe('#228be6') // primary.600
    expect(THEME_COLOR_LIGHT).toBe('#ffffff') // ui.bg
    expect(THEME_COLOR_DARK).toBe('#1a1b1e') // ui-dark.bg
    expect(BACKGROUND_COLOR).toBe(THEME_COLOR_LIGHT)
  })
})

describe('icon paths', () => {
  it('offers the two sizes a manifest is expected to carry', () => {
    expect(ICON_SIZES).toEqual([192, 512])
  })

  it('points at the committed PNGs, which is what the paths on disk are called', () => {
    expect(ICON_SIZES.map(iconPath)).toEqual([
      '/icons/icon-192.png',
      '/icons/icon-512.png',
    ])
  })

  it('keeps the Apple icon at the size iOS actually asks for', () => {
    // iOS uses apple-touch-icon for the Home Screen, not the manifest icons
    expect(APPLE_ICON_SIZE).toBe(180)
    expect(APPLE_ICON_PATH).toBe('/icons/apple-icon-180.png')
  })
})
