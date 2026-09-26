import { render, screen, within } from '@testing-library/react'

import IconSpikePage from '../page'
import results from '@/public/icon-spike/results.json'

describe('/components-demo/icons (Q18 spike)', () => {
  it('renders one row per product in the spike results', () => {
    render(<IconSpikePage />)

    const rows = screen.getAllByTestId('icon-row')
    expect(results.products.length).toBeGreaterThanOrEqual(15)
    expect(rows).toHaveLength(results.products.length)
    results.products.forEach((product, i) => {
      expect(within(rows[i]).getByRole('heading', { name: product.name })).toBeInTheDocument()
    })
  })

  it('shows the category emoji, the picked icon and the drawn icon side by side', () => {
    render(<IconSpikePage />)

    const first = screen.getAllByTestId('icon-row')[0]
    const product = results.products[0]
    expect(within(first).getAllByText(product.category_icon).length).toBeGreaterThan(0)
    expect(within(first).getAllByText(/today/i).length).toBeGreaterThan(0)
    expect(within(first).getAllByText(/\(a\) picked/i).length).toBeGreaterThan(0)
    expect(within(first).getAllByText(/\(b\) drawn/i).length).toBeGreaterThan(0)
  })

  it('renders generated SVGs only as <img src>, never inline', () => {
    const { container } = render(<IconSpikePage />)

    const drawn = Array.from(container.querySelectorAll('img')).filter((img) =>
      (img.getAttribute('src') ?? '').startsWith('/icon-spike/generated/')
    )
    const withDrawing = results.products.filter((p) => p.draw?.file)
    expect(withDrawing.length).toBeGreaterThan(0)
    // Every drawing appears at two sizes in two themes.
    expect(drawn).toHaveLength(withDrawing.length * 4)
    // Nothing the model wrote is inlined into the DOM.
    expect(container.querySelector('svg path, svg circle, svg rect')).toBeNull()
  })
})
