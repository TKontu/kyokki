/**
 * The two App Router error boundaries (H04). There were none at all before, so anything that
 * threw during render left the always-on iPad on a blank white page until someone reloaded it.
 */

import React from 'react'
import { act, render, screen } from '@testing-library/react'
import { AUTO_RETRY_MS } from '@/components/ui/ErrorScreen'
import ErrorBoundary from '../error'
import GlobalError from '../global-error'

afterEach(() => jest.useRealTimers())

describe('app/error.tsx', () => {
  it('shows the error and retries itself', () => {
    jest.useFakeTimers()
    const reset = jest.fn()
    render(<ErrorBoundary error={new Error('render exploded')} reset={reset} />)

    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('render exploded')).toBeInTheDocument()

    act(() => {
      jest.advanceTimersByTime(AUTO_RETRY_MS)
    })
    expect(reset).toHaveBeenCalledTimes(1)
  })
})

describe('app/global-error.tsx', () => {
  // This one replaces the root layout, so it has to render its own <html>/<body>. Next mounts it
  // at the document root; RTL mounts it in a <div>, which React quite rightly complains about.
  // The warning is an artefact of the harness, not of the component, so it is silenced here and
  // only here -- every other console.error still shows.
  let nesting: jest.SpyInstance

  beforeEach(() => {
    nesting = jest.spyOn(console, 'error').mockImplementation((...args) => {
      if (typeof args[0] === 'string' && args[0].includes('validateDOMNesting')) return
      // eslint-disable-next-line no-console
      console.warn(...args)
    })
  })

  afterEach(() => nesting.mockRestore())

  it('shows the error and retries itself', () => {
    jest.useFakeTimers()
    const reset = jest.fn()
    render(<GlobalError error={new Error('layout exploded')} reset={reset} />)

    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('layout exploded')).toBeInTheDocument()

    act(() => {
      jest.advanceTimersByTime(AUTO_RETRY_MS)
    })
    expect(reset).toHaveBeenCalledTimes(1)
  })
})
