// Learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom'

// Tests mock the API with absolute URLs (msw handlers build them from this
// variable). The app itself defaults to the same-origin '/api' path.
process.env.NEXT_PUBLIC_API_URL = 'http://localhost:8000/api'

// Polyfills for test environment
import { TextEncoder, TextDecoder } from 'util'
import 'whatwg-fetch'

global.TextEncoder = TextEncoder
global.TextDecoder = TextDecoder
