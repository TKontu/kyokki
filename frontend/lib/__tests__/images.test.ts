/**
 * Downscaling a photographed receipt before upload (MVP-R6).
 */

import { downscaleImage, MAX_EDGE, shouldDownscale, targetSize } from '../images'

const file = (name: string, type: string, bytes = 5_000_000) =>
  new File([new Uint8Array(bytes)], name, { type })

describe('shouldDownscale', () => {
  it('shrinks photos', () => {
    expect(shouldDownscale(file('receipt.jpg', 'image/jpeg'))).toBe(true)
    expect(shouldDownscale(file('receipt.png', 'image/png'))).toBe(true)
  })

  it('leaves a PDF alone: it is small already and the text path needs it intact', () => {
    expect(shouldDownscale(file('receipt.pdf', 'application/pdf'))).toBe(false)
  })
})

describe('targetSize', () => {
  it('caps the long edge and keeps the aspect ratio', () => {
    expect(targetSize(4000, 3000)).toEqual({ width: MAX_EDGE, height: 1500 })
    expect(targetSize(3000, 4000)).toEqual({ width: 1500, height: MAX_EDGE })
  })

  it('leaves an image that already fits', () => {
    expect(targetSize(1600, 1200)).toBeNull()
    expect(targetSize(MAX_EDGE, 100)).toBeNull()
  })

  it('never rounds an edge away to nothing', () => {
    expect(targetSize(10_000, 3, 2000)).toEqual({ width: 2000, height: 1 })
  })

  it('shrugs at a zero-sized image instead of dividing by it', () => {
    expect(targetSize(0, 0)).toBeNull()
  })
})

describe('downscaleImage', () => {
  const originalCreate = global.createImageBitmap

  afterEach(() => {
    global.createImageBitmap = originalCreate
    jest.restoreAllMocks()
  })

  it('returns a PDF untouched without decoding it', async () => {
    const decode = jest.fn()
    global.createImageBitmap = decode as unknown as typeof createImageBitmap
    const pdf = file('receipt.pdf', 'application/pdf')

    expect(await downscaleImage(pdf)).toBe(pdf)
    expect(decode).not.toHaveBeenCalled()
  })

  it('keeps the original when the browser cannot decode the image', async () => {
    global.createImageBitmap = jest
      .fn()
      .mockRejectedValue(new Error('unsupported')) as unknown as typeof createImageBitmap
    const photo = file('receipt.jpg', 'image/jpeg')

    expect(await downscaleImage(photo)).toBe(photo)
  })

  it('keeps the original when the image already fits', async () => {
    global.createImageBitmap = jest
      .fn()
      .mockResolvedValue({ width: 1000, height: 800, close: jest.fn() }) as unknown as typeof createImageBitmap
    const photo = file('receipt.jpg', 'image/jpeg')

    expect(await downscaleImage(photo)).toBe(photo)
  })

  it('returns a smaller JPEG when the photo is oversized', async () => {
    global.createImageBitmap = jest
      .fn()
      .mockResolvedValue({ width: 4000, height: 3000, close: jest.fn() }) as unknown as typeof createImageBitmap
    const small = new Blob([new Uint8Array(100_000)], { type: 'image/jpeg' })
    jest.spyOn(document, 'createElement').mockReturnValue({
      width: 0,
      height: 0,
      getContext: () => ({ drawImage: jest.fn() }),
      toBlob: (cb: (blob: Blob) => void) => cb(small),
    } as unknown as HTMLCanvasElement)

    const result = await downscaleImage(file('receipt.png', 'image/png'))

    expect(result.size).toBe(100_000)
    expect(result.type).toBe('image/jpeg')
    // Re-encoded, so the name follows
    expect(result.name).toBe('receipt.jpg')
  })
})
