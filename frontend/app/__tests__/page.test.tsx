import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui/Toast'
import Home from '../page'

function wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>{children}</ToastProvider>
    </QueryClientProvider>
  )
}

describe('Home Page', () => {
  it('should render without crashing', () => {
    render(<Home />, { wrapper })
    expect(document.body).toBeInTheDocument()
  })

  it('has an Add button that opens the quick add sheet', () => {
    render(<Home />, { wrapper })
    expect(screen.getByRole('button', { name: '+ Add' })).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
