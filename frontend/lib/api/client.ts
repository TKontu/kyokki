/**
 * API Client
 * Base fetch wrapper with error handling
 */

import { APIError, NetworkError } from './errors'
import type { APIConfig, QueryValue, RequestOptions } from '@/types/api'

/**
 * Human-readable message for a failed response. FastAPI sends `{ detail: string }` for
 * HTTPException and `{ detail: [{ msg, ... }] }` for validation errors.
 */
function errorMessage(
  errorData: { message?: unknown; detail?: unknown },
  response: { status: number; statusText: string }
): string {
  if (typeof errorData.message === 'string' && errorData.message) {
    return errorData.message
  }
  if (typeof errorData.detail === 'string' && errorData.detail) {
    return errorData.detail
  }
  if (Array.isArray(errorData.detail)) {
    const first = errorData.detail[0] as { msg?: unknown } | undefined
    if (typeof first?.msg === 'string' && first.msg) {
      return first.msg
    }
  }
  // An object detail carries more than a message, e.g. the id of the duplicate receipt
  // that a second upload of the same file collides with (MVP-R6)
  if (errorData.detail && typeof errorData.detail === 'object') {
    const { message } = errorData.detail as { message?: unknown }
    if (typeof message === 'string' && message) {
      return message
    }
  }
  return response.statusText || `Request failed (${response.status})`
}

/** Everything the caller may need beyond the message; FastAPI puts it in `detail`. */
function errorDetails(errorData: {
  details?: unknown
  detail?: unknown
}): Record<string, unknown> | undefined {
  if (errorData.details && typeof errorData.details === 'object') {
    return errorData.details as Record<string, unknown>
  }
  if (
    errorData.detail &&
    typeof errorData.detail === 'object' &&
    !Array.isArray(errorData.detail)
  ) {
    return errorData.detail as Record<string, unknown>
  }
  return undefined
}

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

    // Build query string from params; nothing left to send means no '?' at all
    const query = new URLSearchParams(
      Object.entries(options?.params ?? {}).flatMap(([k, v]) =>
        v === undefined
          ? []
          : Array.isArray(v)
            ? v.map((each) => [k, String(each)])
            : [[k, String(v)]]
      )
    ).toString()
    const queryString = query ? `?${query}` : ''

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
          errorMessage(errorData, response),
          errorDetails(errorData)
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
    params?: Record<string, QueryValue>
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
          errorMessage(errorData, response),
          errorDetails(errorData)
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

// Create default client instance.
// Default is the same-origin path proxied by the Next.js rewrite (next.config.mjs);
// NEXT_PUBLIC_API_URL overrides it when the API is served from another origin.
const apiClient = new APIClient({
  baseURL: process.env.NEXT_PUBLIC_API_URL || '/api',
})

export default apiClient
