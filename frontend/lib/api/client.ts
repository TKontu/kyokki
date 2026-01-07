/**
 * API Client
 * Base fetch wrapper with error handling
 */

import { APIError, NetworkError } from './errors'
import type { APIConfig, RequestOptions } from '@/types/api'

export class APIClient {
  private baseURL: string
  private onError?: (error: APIError) => void

  constructor(config: APIConfig) {
    this.baseURL = config.baseURL
    this.onError = config.onError
  }

  /**
   * Make an HTTP request
   */
  async request<T>(
    method: string,
    path: string,
    options?: RequestOptions
  ): Promise<T> {
    const url = `${this.baseURL}${path}`

    // Build query string from params
    const queryString = options?.params
      ? '?' +
        new URLSearchParams(
          Object.entries(options.params)
            .filter(([, v]) => v !== undefined)
            .map(([k, v]) => [k, String(v)])
        ).toString()
      : ''

    try {
      const response = await fetch(url + queryString, {
        method,
        headers: {
          'Content-Type': 'application/json',
          ...options?.headers,
        },
        body: options?.body ? JSON.stringify(options.body) : undefined,
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        const error = new APIError(
          response.status,
          errorData.code || 'UNKNOWN_ERROR',
          errorData.message || response.statusText,
          errorData.details
        )
        this.onError?.(error)
        throw error
      }

      // Handle 204 No Content
      if (response.status === 204) {
        return undefined as T
      }

      return response.json()
    } catch (error) {
      if (error instanceof APIError) {
        throw error
      }
      // Network error - connection failed, timeout, etc.
      throw new NetworkError(
        error instanceof Error ? error.message : 'Network request failed'
      )
    }
  }

  /**
   * GET request
   */
  async get<T>(
    path: string,
    params?: Record<string, string | number | boolean | undefined>
  ): Promise<T> {
    return this.request<T>('GET', path, { params })
  }

  /**
   * POST request
   */
  async post<T>(path: string, body: unknown): Promise<T> {
    return this.request<T>('POST', path, { body })
  }

  /**
   * PATCH request
   */
  async patch<T>(path: string, body: unknown): Promise<T> {
    return this.request<T>('PATCH', path, { body })
  }

  /**
   * PUT request
   */
  async put<T>(path: string, body: unknown): Promise<T> {
    return this.request<T>('PUT', path, { body })
  }

  /**
   * DELETE request
   */
  async delete<T>(path: string): Promise<T> {
    return this.request<T>('DELETE', path)
  }

  /**
   * Upload file with multipart/form-data
   */
  async upload<T>(path: string, file: File, additionalData?: Record<string, string>): Promise<T> {
    const url = `${this.baseURL}${path}`
    const formData = new FormData()
    formData.append('file', file)

    if (additionalData) {
      Object.entries(additionalData).forEach(([key, value]) => {
        formData.append(key, value)
      })
    }

    try {
      const response = await fetch(url, {
        method: 'POST',
        body: formData,
        // Don't set Content-Type header - browser will set it with boundary
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        const error = new APIError(
          response.status,
          errorData.code || 'UNKNOWN_ERROR',
          errorData.message || response.statusText,
          errorData.details
        )
        this.onError?.(error)
        throw error
      }

      return response.json()
    } catch (error) {
      if (error instanceof APIError) {
        throw error
      }
      throw new NetworkError(
        error instanceof Error ? error.message : 'Upload failed'
      )
    }
  }
}

// Create default client instance
const apiClient = new APIClient({
  baseURL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api',
})

export default apiClient
