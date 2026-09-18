// Learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom'
import { configure } from '@testing-library/react'

// RTL's default budget for findBy*/waitFor is 1000 ms, which is the same order as the work some
// of these tests wait on: the product search debounces 250 ms before it even asks, and jest runs
// suites in parallel on a machine that is also building. That made green depend on the load
// average. 5000 ms (with the matching testTimeout in jest.config.js, so the assertion's own
// error wins over jest's) turns a slow machine back into a slow run instead of a red one (H06).
configure({ asyncUtilTimeout: 5000 })

// Tests mock the API with absolute URLs (msw handlers build them from this
// variable). The app itself defaults to the same-origin '/api' path.
process.env.NEXT_PUBLIC_API_URL = 'http://localhost:8000/api'

// Fetch, streams and TextEncoder globals come from jest.polyfills.js (setupFiles).
