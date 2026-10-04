import type { MetadataRoute } from 'next'
import { BACKGROUND_COLOR, BRAND_COLOR, BRAND_NAME, ICON_SIZES, iconPath } from '@/lib/brand'

/**
 * Web app manifest (MVP-P2), served at /manifest.webmanifest.
 *
 * This is what turns Add to Home Screen on the iPad into a full-screen app rather than a
 * bookmark. iOS also needs the `appleWebApp` metadata in `app/layout.tsx`, and it ignores
 * `orientation` for home-screen web apps - the wall mount decides that. The iPad is mounted
 * upright (Q17), so the app asks for portrait where a platform listens.
 *
 * Production is served over HTTPS, so Android Chrome can install the app. There is still no
 * service worker yet; offline stays post-MVP.
 *
 * `share_target` makes the installed app a target in Android's share sheet: shared receipt
 * photos and PDFs are posted to /api/receipts/share, which queues each one and redirects to
 * the receipt, the receipt list, or the scan page with a failure note.
 */
/**
 * Web Share Target as the W3C spec defines it. Next 14's `MetadataRoute.Manifest` types
 * `share_target` with lowercase methods and `params` as a name/value array, which is not
 * the shape Chrome reads, so the field is replaced with the spec's shape here.
 */
interface ShareTarget {
  action: string
  method: 'GET' | 'POST'
  enctype: 'application/x-www-form-urlencoded' | 'multipart/form-data'
  params: {
    title?: string
    text?: string
    url?: string
    files?: { name: string; accept: string[] }[]
  }
}

type KyokkiManifest = Omit<MetadataRoute.Manifest, 'share_target'> & {
  share_target: ShareTarget
}

export default function manifest(): KyokkiManifest {
  return {
    name: BRAND_NAME,
    short_name: BRAND_NAME,
    description: 'Kitchen inventory: what is in the fridge, and what is about to go off.',
    start_url: '/',
    scope: '/',
    display: 'standalone',
    orientation: 'portrait',
    background_color: BACKGROUND_COLOR,
    theme_color: BRAND_COLOR,
    icons: ICON_SIZES.map((size) => ({
      src: iconPath(size),
      sizes: `${size}x${size}`,
      type: 'image/png',
    })),
    share_target: {
      action: '/api/receipts/share',
      method: 'POST',
      enctype: 'multipart/form-data',
      params: {
        title: 'title',
        text: 'text',
        url: 'url',
        files: [{ name: 'receipts', accept: ['image/*', 'application/pdf'] }],
      },
    },
  }
}
