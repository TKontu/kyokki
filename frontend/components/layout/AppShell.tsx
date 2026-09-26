'use client'

/**
 * AppShell (MVP-P1)
 * The one persistent piece of navigation. A narrow rail down the left in landscape, which is
 * where the iPad has room to spare; a bar across the top on a phone, where it does not.
 * Pages keep their own header and their own actions.
 */

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { StatusBanner } from './StatusBanner'

interface Destination {
  href: string
  label: string
  icon: string
  /** Sub-routes that belong to this destination, e.g. a receipt opened from the list. */
  owns?: (pathname: string) => boolean
}

export const DESTINATIONS: Destination[] = [
  { href: '/', label: 'Stock', icon: '🧊' },
  { href: '/scan', label: 'Scan', icon: '📷' },
  {
    href: '/receipts',
    label: 'Receipts',
    icon: '🧾',
    // /receipt/<id> is a receipt opened from this list
    owns: (pathname) => pathname.startsWith('/receipt'),
  },
  // The catalog (Q11). Until it existed the product editor could only be reached from an
  // item that happened to be in stock, so most products could not be corrected at all.
  { href: '/products', label: 'Products', icon: '🏷️' },
  // What left the kitchen, and the waste it cost (2026-09-22). The only screen that lists
  // items no longer in stock, which is what makes "Put it back" reachable at all.
  { href: '/gone', label: 'Gone', icon: '🗑️' },
]

export function isActive(destination: Destination, pathname: string): boolean {
  if (pathname === destination.href) return true
  return destination.owns?.(pathname) ?? false
}

const linkClass = [
  'flex min-h-touch-lg flex-1 flex-col items-center justify-center gap-0.5 rounded-ui',
  'px-2 py-2 text-xs font-medium no-select lg:flex-none',
  'text-ui-text-secondary dark:text-ui-dark-text-secondary',
  'hover:bg-ui-bg-secondary dark:hover:bg-ui-dark-bg-secondary',
].join(' ')

const activeClass =
  'bg-primary-50 text-primary-700 dark:bg-ui-dark-bg-tertiary dark:text-primary-200'

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() ?? '/'

  return (
    <div className="flex min-h-screen flex-col bg-ui-bg dark:bg-ui-dark-bg lg:flex-row">
      <nav
        aria-label="Main"
        className={[
          'flex shrink-0 gap-1 border-ui-border bg-ui-bg-secondary p-1',
          'dark:border-ui-dark-border dark:bg-ui-dark-bg-secondary',
          'border-b lg:w-20 lg:flex-col lg:border-b-0 lg:border-r lg:p-2',
          'pl-[env(safe-area-inset-left)] pt-[env(safe-area-inset-top)] lg:pt-2',
        ].join(' ')}
      >
        {DESTINATIONS.map((destination) => {
          const active = isActive(destination, pathname)
          return (
            <Link
              key={destination.href}
              href={destination.href}
              aria-current={active ? 'page' : undefined}
              className={`${linkClass} ${active ? activeClass : ''}`}
            >
              <span aria-hidden="true" className="text-xl leading-none">
                {destination.icon}
              </span>
              {destination.label}
            </Link>
          )
        })}
      </nav>
      {/* A column, so a page can take the height left under the bar: the fridge fills it */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Above every screen, and silent unless something is wrong (H45) */}
        <StatusBanner />
        {children}
      </div>
    </div>
  )
}

export default AppShell
