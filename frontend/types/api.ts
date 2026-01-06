/**
 * API Types
 * Common types for API requests and responses
 */

export class APIError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown
  ) {
    super(message)
    this.name = 'APIError'
  }
}

export class NetworkError extends Error {
  constructor(message: string = 'Network request failed') {
    super(message)
    this.name = 'NetworkError'
  }
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface RequestOptions {
  headers?: Record<string, string>
  params?: Record<string, string | number | boolean | undefined>
  body?: unknown
}

export interface APIConfig {
  baseURL: string
  onError?: (error: APIError) => void
}

// Type guards
export function isAPIError(error: unknown): error is APIError {
  return error instanceof APIError
}

export function isNetworkError(error: unknown): error is NetworkError {
  return error instanceof NetworkError
}
