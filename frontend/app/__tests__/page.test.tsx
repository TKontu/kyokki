import { render } from '@testing-library/react'
import Home from '../page'

describe('Home Page', () => {
  it('should render without crashing', () => {
    render(<Home />)
    // Smoke test - just verify the page renders without errors
    expect(document.body).toBeInTheDocument()
  })
})
