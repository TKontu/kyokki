/**
 * Icon curation (operator ask 2026-10-03): status, mark/unmark, the marked list, and the
 * bundle download URL.
 */

import iconLibraryAPI, {
  bundleUrl,
  getStatus,
  listMarks,
  markIcon,
  unmarkIcon,
} from '../iconLibrary'
import { server, API_URL } from '@/test/msw/server'
import { http, HttpResponse } from 'msw'

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('getStatus', () => {
  it('returns the curation status', async () => {
    server.use(
      http.get(`${API_URL}/icon-library/status`, () =>
        HttpResponse.json({ curation_enabled: true, library_count: 5, marked_count: 2 })
      )
    )

    const status = await getStatus()

    expect(status).toEqual({ curation_enabled: true, library_count: 5, marked_count: 2 })
  })
})

describe('markIcon', () => {
  it('PUTs the mark and returns the entry', async () => {
    let method = ''
    server.use(
      http.put(`${API_URL}/icon-library/marks/p-1`, ({ request }) => {
        method = request.method
        return HttpResponse.json({
          id: 'p-1',
          name: 'Quark',
          icon_version: 123,
          marked_at: '2026-10-03T12:00:00Z',
        })
      })
    )

    const entry = await markIcon('p-1')

    expect(method).toBe('PUT')
    expect(entry.marked_at).toBe('2026-10-03T12:00:00Z')
  })

  it('escapes the id', async () => {
    let path = ''
    server.use(
      http.put(`${API_URL}/icon-library/marks/:id`, ({ params, request }) => {
        path = new URL(request.url).pathname
        return HttpResponse.json({
          id: String(params.id),
          name: 'x',
          icon_version: null,
          marked_at: null,
        })
      })
    )

    await markIcon('a/b')

    expect(path).toBe('/api/icon-library/marks/a%2Fb')
  })
})

describe('unmarkIcon', () => {
  it('DELETEs the mark and returns the entry with marked_at null', async () => {
    server.use(
      http.delete(`${API_URL}/icon-library/marks/p-1`, () =>
        HttpResponse.json({ id: 'p-1', name: 'Quark', icon_version: 123, marked_at: null })
      )
    )

    const entry = await unmarkIcon('p-1')

    expect(entry.marked_at).toBeNull()
  })
})

describe('listMarks', () => {
  it('returns the marked list', async () => {
    server.use(
      http.get(`${API_URL}/icon-library/marks`, () =>
        HttpResponse.json([
          { id: 'p-1', name: 'Quark', icon_version: 1, marked_at: '2026-10-03T00:00:00Z' },
        ])
      )
    )

    const marks = await listMarks()

    expect(marks).toHaveLength(1)
    expect(marks[0].name).toBe('Quark')
  })
})

describe('bundleUrl', () => {
  it('points at the bundle endpoint', () => {
    expect(bundleUrl()).toBe(`${API_URL}/icon-library/bundle.zip`)
  })

  it('is on the default export too', () => {
    expect(iconLibraryAPI.bundleUrl).toBe(bundleUrl)
  })
})
