import type { MetadataRoute } from 'next'
import { BACKGROUND_COLOR, BRAND_COLOR, BRAND_NAME, ICON_SIZES, iconPath } from '@/lib/brand'

/**
 * Web app manifest (MVP-P2), served at /manifest.webmanifest.
 *
 * This is what turns Add to Home Screen on the iPad into a full-screen app rather than a
 * bookmark. iOS also needs the `appleWebApp` metadata in `app/layout.tsx`, and it ignores
 * `orientation` for home-screen web apps - the wall mount decides that.
 *
 * No service worker: the stack is served over plain HTTP on the LAN, which is not a secure
 * context, so registration would be refused. Offline stays post-MVP for that reason.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: BRAND_NAME,
    short_name: BRAND_NAME,
    description: 'Kitchen inventory: what is in the fridge, and what is about to go off.',
    start_url: '/',
    scope: '/',
    display: 'standalone',
    orientation: 'landscape',
    background_color: BACKGROUND_COLOR,
    theme_color: BRAND_COLOR,
    icons: ICON_SIZES.map((size) => ({
      src: iconPath(size),
      sizes: `${size}x${size}`,
      type: 'image/png',
    })),
  }
}
