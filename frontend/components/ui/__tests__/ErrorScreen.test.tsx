/**
 * The crash screen on the kitchen iPad (H04): nobody is standing there, so it has to get itself
 * out of the error without a tap, while still offering one to whoever is.
 */

import React from 'react'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { AUTO_RETRY_MS, ErrorScreen } from '../ErrorScreen'

afterEach(() => jest.useRealTimers())

function renderScreen(error: Error & { digest?: string } = new Error('boom')) {
  const reset = jest.fn()
  render(<ErrorScreen error={error} reset={reset} />)
  return reset
}

describe('ErrorScreen', () => {
  it('says what happened without showing a blank page', () => {
    renderScreen()
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
    expect(screen.getByText('boom')).toBeInTheDocument()
  })

  it("includes Next's digest when there is one", () => {
    renderScreen(Object.assign(new Error('server blew up'), { digest: 'abc123' }))
    expect(screen.getByText('server blew up (abc123)')).toBeInTheDocument()
  })

  it('retries on its own after the delay, with nobody touching it', () => {
    jest.useFakeTimers()
    const reset = renderScreen()

    act(() => {
      jest.advanceTimersByTime(AUTO_RETRY_MS - 1)
    })
    expect(reset).not.toHaveBeenCalled()

    act(() => {
      jest.advanceTimersByTime(1)
    })
    expect(reset).toHaveBeenCalledTimes(1)
  })

  it('also retries when someone taps Try again', () => {
    jest.useFakeTimers()
    const reset = renderScreen()

    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(reset).toHaveBeenCalledTimes(1)
  })

  it('drops its timer when it unmounts, so a recovered page is not reset under it', () => {
    jest.useFakeTimers()
    const reset = jest.fn()
    const { unmount } = render(<ErrorScreen error={new Error('boom')} reset={reset} />)

    unmount()
    act(() => {
      jest.advanceTimersByTime(AUTO_RETRY_MS * 2)
    })
    expect(reset).not.toHaveBeenCalled()
  })
})
