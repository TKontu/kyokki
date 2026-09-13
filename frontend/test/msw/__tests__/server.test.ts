import { http, HttpResponse } from 'msw'
import { server, API_URL } from '../server'
import apiClient from '@/lib/api/client'

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('msw test server', () => {
  it('intercepts requests made through the API client', async () => {
    server.use(http.get(`${API_URL}/ping`, () => HttpResponse.json({ ok: true })))

    await expect(apiClient.get('/ping')).resolves.toEqual({ ok: true })
  })
})
