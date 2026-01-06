import { APIClient } from '../client'
import { APIError, NetworkError, isAPIError, isNetworkError } from '../errors'

// Mock global fetch
const mockFetch = jest.fn()
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
