/**
 * msw request interception for Jest.
 * No default handlers: each test registers what it needs with `server.use(...)`.
 * Not started globally, so tests that mock `global.fetch` directly are unaffected.
 */
import { setupServer } from 'msw/node'

export const server = setupServer()

export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api'
