import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { ToastProvider } from '@/components/ui/Toast'
import Home from '../page'

// Home mounts InventoryList and ReceiptsBanner, which fetch on mount. Without msw those two
// requests went to a real localhost:8000: undici opened a socket, nothing was listening, and the
// connection error landed on a socket whose request had already been thrown away when the test
// finished. Node has no listener for that, so it killed the worker -- the "a worker process has
// failed to exit gracefully" warning at the end of every run, which jest does not fail on (H06).
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>{children}</ToastProvider>
    </QueryClientProvider>
  )
}

function mockApi() {
  server.use(
    http.get(`${API_URL}/inventory`, () => HttpResponse.json([])),
    http.get(`${API_URL}/inventory/undo`, () => HttpResponse.json(null)),
    http.get(`${API_URL}/receipts`, () => HttpResponse.json([]))
  )
}

describe('Home Page', () => {
  it('should render without crashing', async () => {
    mockApi()
    render(<Home />, { wrapper })
    expect(document.body).toBeInTheDocument()
    // Let both queries settle inside the test, so nothing is still in flight at teardown
    await screen.findByText(/no items found/i)
  })

  it('names the page for screen readers only, so the fridge gets the room (Q20)', async () => {
    mockApi()
    render(<Home />, { wrapper })

    const title = screen.getByRole('heading', { level: 1, name: 'Kyokki' })
    expect(title).toHaveClass('sr-only')
    // Undo and + Add stay on the page, not in the app's bar
    expect(screen.getByRole('button', { name: '+ Add' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Undo/ })).toBeInTheDocument()
    await screen.findByText(/no items found/i)
  })

  it('stands the fridge on the warm beige scene, in both themes (Q29)', async () => {
    mockApi()
    const { container } = render(<Home />, { wrapper })

    // A token, not a literal: the dark theme swaps its value for a warm dark one
    expect(container.firstElementChild).toHaveClass('bg-fridge-scene')
    await screen.findByText(/no items found/i)
  })

  it('has an Add button that opens the quick add sheet', async () => {
    mockApi()
    render(<Home />, { wrapper })
    expect(screen.getByRole('button', { name: '+ Add' })).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await screen.findByText(/no items found/i)
  })
})
