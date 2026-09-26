'use client'

/**
 * Fridge design mocks (Q17-M): the operator picks the fridge that replaces FridgeView on `/`.
 *
 * Every design on live stock, with sample stock for an empty homelab, and - last, "Upright" -
 * the fridge `/` now draws (Q17-B: Cielo redrawn for portrait), to compare against the mocks
 * on the upright iPad (810×1080). The page takes the height under the app's bar and nothing
 * scrolls. The address can name the starting state, for screenshots:
 * `?design=portrait&sample=on&theme=dark`.
 */

import React, { useEffect, useMemo, useState } from 'react'
import { CieloFridge } from '@/components/fridge/CieloFridge'
import { FRIDGE_MOCKS, fixtureItems, type FridgeMock } from '@/components/fridge-mocks'
import { useInventoryList } from '@/hooks/useInventory'

/** The mocks, and the production fridge they led to. */
const DESIGNS: FridgeMock[] = [
  ...FRIDGE_MOCKS,
  {
    id: 'portrait',
    name: 'Upright',
    description: 'Cielo for the portrait iPad, as on Stock',
    Component: CieloFridge,
  },
]

type Theme = 'auto' | 'light' | 'dark'

const THEMES: { id: Theme; label: string }[] = [
  { id: 'auto', label: 'Auto' },
  { id: 'light', label: 'Light' },
  { id: 'dark', label: 'Dark' },
]

const segment =
  'min-h-touch rounded-xl px-3 text-left focus:outline-none ' +
  'focus-visible:ring-2 focus-visible:ring-primary-400 '
const segmentOn =
  'bg-ui-bg text-ui-text shadow-ui-sm dark:bg-ui-dark-bg-tertiary dark:text-ui-dark-text'
const segmentOff =
  'text-ui-text-secondary hover:bg-ui-bg/60 dark:text-ui-dark-text-secondary dark:hover:bg-ui-dark-bg/60'

export default function FridgeMocksPage() {
  const [designId, setDesignId] = useState(DESIGNS[0].id)
  const [sample, setSample] = useState(false)
  const [theme, setTheme] = useState<Theme>('auto')
  const live = useInventoryList()
  const samples = useMemo(() => fixtureItems(), [])

  // The starting state from the address, once, so a screenshot can ask for a design directly
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const design = params.get('design')
    if (design && DESIGNS.some((mock) => mock.id === design)) setDesignId(design)
    if (params.get('sample') === 'on') setSample(true)
    const asked = params.get('theme')
    if (asked === 'light' || asked === 'dark') setTheme(asked)
  }, [])

  useEffect(() => {
    const root = document.documentElement
    root.classList.remove('light', 'dark')
    if (theme !== 'auto') root.classList.add(theme)
    return () => root.classList.remove('light', 'dark')
  }, [theme])

  const design = DESIGNS.find((mock) => mock.id === designId) ?? DESIGNS[0]
  const Fridge = design.Component
  const items = sample ? samples : live.data

  let body: React.ReactNode
  if (!sample && live.isLoading) {
    body = (
      <div
        aria-label="Loading inventory"
        className="h-full animate-pulse rounded-3xl bg-ui-bg-tertiary dark:bg-ui-dark-bg-tertiary"
      />
    )
  } else if (!sample && live.isError && !live.data) {
    body = (
      <p role="alert" className="py-4 text-sm text-red-600 dark:text-red-400">
        {live.error instanceof Error ? live.error.message : 'Failed to load inventory.'}
      </p>
    )
  } else {
    body = <Fridge items={items ?? []} onConsume={() => {}} onMore={() => {}} onClearExpired={() => {}} />
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden bg-ui-bg px-4 py-3 dark:bg-ui-dark-bg">
      <header className="flex shrink-0 flex-wrap items-center gap-3">
        <h1 className="w-20 text-sm font-semibold leading-tight text-ui-text dark:text-ui-dark-text">
          Fridge designs
        </h1>
        <div
          role="group"
          aria-label="Design"
          className="order-last flex min-w-0 basis-full gap-1 rounded-2xl bg-ui-bg-tertiary p-1 dark:bg-ui-dark-bg-secondary xl:order-none xl:basis-0 xl:flex-1"
        >
          {DESIGNS.map((mock) => {
            const on = mock.id === design.id
            return (
              <button
                key={mock.id}
                type="button"
                aria-pressed={on}
                onClick={() => setDesignId(mock.id)}
                className={`${segment} min-w-0 flex-1 py-1 ${on ? segmentOn : segmentOff}`}
              >
                <span className="block text-sm font-semibold">{mock.name}</span>
                <span className="block truncate text-xs opacity-80">{mock.description}</span>
              </button>
            )
          })}
        </div>
        <button
          type="button"
          aria-pressed={sample}
          onClick={() => setSample((on) => !on)}
          className={
            'ml-auto min-h-touch shrink-0 rounded-2xl border-2 px-3 text-sm font-medium xl:ml-0 ' +
            (sample
              ? 'border-primary-500 bg-primary-50 text-primary-800 dark:border-primary-400 dark:bg-primary-900/40 dark:text-primary-100'
              : 'border-ui-border-strong text-ui-text-secondary dark:border-ui-dark-border-strong dark:text-ui-dark-text-secondary')
          }
        >
          Sample stock
        </button>
        <div
          role="group"
          aria-label="Theme"
          className="flex shrink-0 gap-1 rounded-2xl bg-ui-bg-tertiary p-1 dark:bg-ui-dark-bg-secondary"
        >
          {THEMES.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              aria-pressed={theme === id}
              onClick={() => setTheme(id)}
              className={`${segment} text-sm font-medium ${theme === id ? segmentOn : segmentOff}`}
            >
              {label}
            </button>
          ))}
        </div>
      </header>
      <main className="min-h-0 flex-1">{body}</main>
    </div>
  )
}
