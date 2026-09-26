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

  it('keeps the light panel light even when <html> has .dark', () => {
    // Tailwind's `dark:` variant matches `.dark *`, so any `dark:` class inside the light panel
    // would turn it dark under the /components-demo toggle or the browser check.
    const { container } = render(<IconSpikePage />)

    const lightPanels = container.querySelectorAll('[data-panel-theme="light"]')
    const darkPanels = container.querySelectorAll('[data-panel-theme="dark"]')
    expect(lightPanels).toHaveLength(results.products.length)
    expect(darkPanels).toHaveLength(results.products.length)
    lightPanels.forEach((panel) => {
      const classes = [panel, ...Array.from(panel.querySelectorAll('*'))]
        .map((el) => el.getAttribute('class') ?? '')
        .join(' ')
      expect(classes).not.toMatch(/(^|\s)dark:/)
    })
  })

  it('credits OpenMoji with a link to its licence', () => {
    render(<IconSpikePage />)

    expect(screen.getByRole('link', { name: 'OpenMoji' })).toHaveAttribute(
      'href',
      'https://openmoji.org'
    )
    expect(screen.getByRole('link', { name: 'CC BY-SA 4.0' })).toHaveAttribute(
      'href',
      'https://creativecommons.org/licenses/by-sa/4.0/'
    )
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
