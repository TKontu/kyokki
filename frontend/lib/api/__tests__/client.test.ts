import { APIClient } from '../client'
import { APIError, NetworkError, isAPIError, isNetworkError } from '../errors'

// Mock global fetch
const mockFetch = jest.fn()
// eslint-disable-next-line @typescript-eslint/no-explicit-any
global.fetch = mockFetch as any

describe('APIClient', () => {
  let client: APIClient
  const BASE_URL = 'http://localhost:8000/api'

  beforeEach(() => {
    client = new APIClient({ baseURL: BASE_URL })
    mockFetch.mockClear()
  })

  describe('GET requests', () => {
    it('should make successful GET request', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ data: 'success' }),
      })

      const result = await client.get<{ data: string }>('/test')
      expect(result).toEqual({ data: 'success' })
      expect(mockFetch).toHaveBeenCalledWith(
        `${BASE_URL}/test`,
        expect.objectContaining({ method: 'GET' })
      )
    })

    it('should include query parameters', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({}),
      })

      await client.get('/test', { param1: 'value1', param2: 'value2' })
      expect(mockFetch).toHaveBeenCalledWith(
        `${BASE_URL}/test?param1=value1&param2=value2`,
        expect.any(Object)
      )
    })

    it('should filter undefined query parameters', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({}),
      })

      await client.get('/test', { param1: 'value1', param2: undefined })
      expect(mockFetch).toHaveBeenCalledWith(
        `${BASE_URL}/test?param1=value1`,
        expect.any(Object)
      )
    })
  })

  describe('POST requests', () => {
    it('should make successful POST request', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ received: { foo: 'bar' } }),
      })

      const result = await client.post('/test', { foo: 'bar' })
      expect(result).toEqual({ received: { foo: 'bar' } })
      expect(mockFetch).toHaveBeenCalledWith(
        `${BASE_URL}/test`,
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ foo: 'bar' }),
        })
      )
    })
  })

  describe('PATCH requests', () => {
    it('should make successful PATCH request', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ updated: true }),
      })

      await client.patch('/test', { foo: 'updated' })
      expect(mockFetch).toHaveBeenCalledWith(
        `${BASE_URL}/test`,
        expect.objectContaining({ method: 'PATCH' })
      )
    })
  })

  describe('DELETE requests', () => {
    it('should handle 204 No Content', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 204,
      })

      const result = await client.delete('/test')
      expect(result).toBeUndefined()
    })

    it('should handle DELETE with JSON response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ deleted: true }),
      })

      const result = await client.delete('/test')
      expect(result).toEqual({ deleted: true })
    })
  })

  describe('Error handling', () => {
    it('should throw APIError on 404', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        status: 404,
        statusText: 'Not Found',
        json: async () => ({
          code: 'NOT_FOUND',
          message: 'Resource not found',
        }),
      })

      await expect(client.get('/test')).rejects.toThrow(APIError)

      // Test the error properties in a separate call
      try {
        await client.get('/test')
      } catch (error) {
        expect(error).toMatchObject({
          status: 404,
          code: 'NOT_FOUND',
          message: 'Resource not found',
        })
      }
    })

    it('should throw APIError on validation error', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        json: async () => ({
          code: 'VALIDATION_ERROR',
          message: 'Invalid input',
          details: { field: 'email' },
        }),
      })

      await expect(client.post('/test', {})).rejects.toMatchObject({
        status: 400,
        code: 'VALIDATION_ERROR',
        details: { field: 'email' },
      })
    })

    it('uses a FastAPI string detail as the error message', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        json: async () => ({ detail: 'Cannot consume 500 - only 100 available' }),
      })

      await expect(client.post('/test', {})).rejects.toMatchObject({
        status: 400,
        message: 'Cannot consume 500 - only 100 available',
      })
    })

    it('uses the first validation message from a FastAPI detail list', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 422,
        statusText: 'Unprocessable Entity',
        json: async () => ({
          detail: [{ loc: ['body', 'quantity'], msg: 'Input should be greater than 0' }],
        }),
      })

      await expect(client.post('/test', {})).rejects.toMatchObject({
        status: 422,
        message: 'Input should be greater than 0',
      })
    })

    it('falls back to a readable message when the body and status text are empty', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 502,
        statusText: '',
        json: async () => {
          throw new Error('not json')
        },
      })

      await expect(client.get('/test')).rejects.toMatchObject({
        status: 502,
        message: 'Request failed (502)',
      })
    })

    it('should throw NetworkError on fetch failure', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network failed'))

      await expect(client.get('/test')).rejects.toThrow(NetworkError)
    })

    it('should call onError callback', async () => {
      const onError = jest.fn()
      const clientWithCallback = new APIClient({
        baseURL: BASE_URL,
        onError,
      })

      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => ({ code: 'ERROR', message: 'Error' }),
      })

      await expect(clientWithCallback.get('/test')).rejects.toThrow()
      expect(onError).toHaveBeenCalledWith(
        expect.objectContaining({ status: 400 })
      )
    })
  })

  describe('upload (MVP-R6)', () => {
    const file = new File(['receipt bytes'], 'receipt.pdf', { type: 'application/pdf' })

    it('posts the file as multipart and lets the browser set the boundary', async () => {
      mockFetch.mockResolvedValueOnce({ ok: true, status: 201, json: async () => ({ id: 'r1' }) })

      const result = await client.upload<{ id: string }>('/receipts/scan', file, {
        store_chain: 's-group',
      })

      expect(result).toEqual({ id: 'r1' })
      const [url, init] = mockFetch.mock.calls[0]
      expect(url).toBe(`${BASE_URL}/receipts/scan`)
      expect(init.method).toBe('POST')
      // A Content-Type of our own would lose the multipart boundary
      expect(init.headers).toBeUndefined()
      const body = init.body as FormData
      expect(body.get('file')).toBe(file)
      expect(body.get('store_chain')).toBe('s-group')
    })

    it('reports an unsupported file type with the message the API gave', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        json: async () => ({ detail: 'Unsupported file type: text/plain' }),
      })

      await expect(client.upload('/receipts/scan', file)).rejects.toMatchObject({
        status: 400,
        message: 'Unsupported file type: text/plain',
      })
    })

    it('keeps the receipt id when the same receipt was already uploaded', async () => {
      // FastAPI returns an object detail here, which used to fall through to statusText
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 409,
        statusText: 'Conflict',
        json: async () => ({
          detail: { message: 'Receipt already uploaded', receipt_id: 'r-existing' },
        }),
      })

      await expect(client.upload('/receipts/scan', file)).rejects.toMatchObject({
        status: 409,
        message: 'Receipt already uploaded',
        details: { message: 'Receipt already uploaded', receipt_id: 'r-existing' },
      })
    })

    it('turns a dropped connection into a NetworkError', async () => {
      mockFetch.mockRejectedValueOnce(new Error('connection reset'))

      await expect(client.upload('/receipts/scan', file)).rejects.toBeInstanceOf(NetworkError)
    })
  })

  describe('Type guards', () => {
    it('should identify APIError', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => ({ code: 'ERROR', message: 'Error' }),
      })

      try {
        await client.get('/test')
      } catch (error) {
        expect(isAPIError(error)).toBe(true)
        expect(isNetworkError(error)).toBe(false)
      }
    })

    it('should identify NetworkError', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network error'))

      try {
        await client.get('/test')
      } catch (error) {
        expect(isNetworkError(error)).toBe(true)
        expect(isAPIError(error)).toBe(false)
      }
    })
  })
})

describe('default apiClient base URL', () => {
  const originalEnv = process.env.NEXT_PUBLIC_API_URL

  afterEach(() => {
    process.env.NEXT_PUBLIC_API_URL = originalEnv
  })

  it('falls back to the same-origin /api path when NEXT_PUBLIC_API_URL is unset', async () => {
    delete process.env.NEXT_PUBLIC_API_URL
    let defaultClient: APIClient | undefined
    jest.isolateModules(() => {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      defaultClient = require('../client').default
    })

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => [],
    })

    await defaultClient!.get('/inventory')
    expect(mockFetch).toHaveBeenCalledWith('/api/inventory', expect.anything())
  })
})
