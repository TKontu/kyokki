/**
 * Icon curation (operator ask 2026-10-03): "The generated -> canonical should be a
 * feature of the 'develop' production build I use. ... during use more [icons] are
 * generated and some are re-generated and after that updated canonical [icons] can be
 * submitted to the repo." On a develop build (`ICON_CURATION_ENABLED` server-side), the
 * cook marks a good generated icon canonical on the product sheet
 * (`ProductEditSheet.tsx`); Settings lists the marked icons and downloads them as one
 * bundle for a PR against the repo's icon library (`backend/scripts/apply_icon_bundle.py`,
 * `docs/icon_library/README.md`).
 */

import apiClient, { API_BASE_URL } from './client'

/** `GET /api/icon-library/status`: whether to show any of this at all. */
export interface IconLibraryStatus {
  curation_enabled: boolean
  library_count: number
  marked_count: number
}

/** One marked product (the mark and unmark routes answer this too; `marked_at` is null
 * right after an unmark). */
export interface IconMarkEntry {
  id: string
  name: string
  icon_version: number | null
  marked_at: string | null // ISO datetime
}

export async function getStatus(): Promise<IconLibraryStatus> {
  return apiClient.get<IconLibraryStatus>('/icon-library/status')
}

/** The cook's "Keep as canonical". 409 when the icon is not a ready, actually-generated
 * image with no emoji win; 404 when curation is disabled on this server. */
export async function markIcon(productId: string): Promise<IconMarkEntry> {
  return apiClient.put<IconMarkEntry>(
    `/icon-library/marks/${encodeURIComponent(productId)}`,
    {}
  )
}

/** Undo a mark. A no-op, not an error, if it was never marked. */
export async function unmarkIcon(productId: string): Promise<IconMarkEntry> {
  return apiClient.delete<IconMarkEntry>(
    `/icon-library/marks/${encodeURIComponent(productId)}`
  )
}

/** Every currently marked product, newest mark first - Settings' own list. */
export async function listMarks(): Promise<IconMarkEntry[]> {
  return apiClient.get<IconMarkEntry[]>('/icon-library/marks')
}

/**
 * Where the bundle downloads from, for Settings' "Download bundle" link - an `<a href>`,
 * not a fetch into the DOM, same reason `iconUrl` in `lib/api/products.ts` is a URL and
 * not a body: the bearer token the middleware adds applies to same-origin `/api` requests
 * either way.
 */
export function bundleUrl(): string {
  return `${API_BASE_URL}/icon-library/bundle.zip`
}

const iconLibraryAPI = { getStatus, markIcon, unmarkIcon, listMarks, bundleUrl }
export default iconLibraryAPI
