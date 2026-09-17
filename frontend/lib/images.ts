/**
 * Shrink a photographed receipt before uploading it (MVP-R6).
 *
 * A 12 MP camera capture is 3-5 MB. The upload endpoint has no size limit of its own, and a
 * huge image costs OCR time without reading any better, so the browser caps the long edge.
 * PDFs are left alone: they are small already and the text path needs them intact.
 */

/** Receipts read fine well below this; it is the long edge in pixels. */
export const MAX_EDGE = 2000
export const JPEG_QUALITY = 0.85

/** Only photos are worth shrinking. */
export function shouldDownscale(file: File): boolean {
  return file.type.startsWith('image/')
}

/** The size to draw at, or null when the image already fits. Keeps the aspect ratio. */
export function targetSize(
  width: number,
  height: number,
  maxEdge: number = MAX_EDGE
): { width: number; height: number } | null {
  const longest = Math.max(width, height)
  if (longest <= maxEdge || longest === 0) return null

  const scale = maxEdge / longest
  return {
    width: Math.max(1, Math.round(width * scale)),
    height: Math.max(1, Math.round(height * scale)),
  }
}

/** Swap the extension for .jpg: the shrunk file is re-encoded as JPEG. */
function jpegName(name: string): string {
  return `${name.replace(/\.[^.]+$/, '')}.jpg`
}

/**
 * Return a smaller JPEG, or the original file when there is nothing to gain.
 *
 * Never throws: an iPad that cannot decode the image still gets to upload it, and the
 * server-side limit (or the lack of one) is the same either way.
 */
export async function downscaleImage(
  file: File,
  { maxEdge = MAX_EDGE, quality = JPEG_QUALITY } = {}
): Promise<File> {
  if (!shouldDownscale(file)) return file

  try {
    const bitmap = await createImageBitmap(file)
    const size = targetSize(bitmap.width, bitmap.height, maxEdge)
    if (!size) {
      bitmap.close?.()
      return file
    }

    const canvas = document.createElement('canvas')
    canvas.width = size.width
    canvas.height = size.height
    const context = canvas.getContext('2d')
    if (!context) return file
    context.drawImage(bitmap, 0, 0, size.width, size.height)
    bitmap.close?.()

    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, 'image/jpeg', quality)
    )
    if (!blob || blob.size >= file.size) return file

    return new File([blob], jpegName(file.name), { type: 'image/jpeg' })
  } catch {
    return file
  }
}
