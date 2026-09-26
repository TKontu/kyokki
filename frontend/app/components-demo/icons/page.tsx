/**
 * Q18 spike: product icons, picked or drawn.
 *
 * A static comparison of what a tile shows today (the category emoji) against the two routes
 * the spike measured: (a) the model picks an OpenMoji icon, (b) the model draws a flat SVG.
 * Each is shown at tile size and at 96 px, in a light and a dark panel side by side.
 *
 * The drawn SVGs came from a model, so they are only ever rendered as `<img src>`: an image
 * loaded that way cannot run script or reach the page, even if sanitising missed something.
 * Data: `public/icon-spike/results.json`, written by `backend/scripts/icon_spike.py`.
 */

import results from '@/public/icon-spike/results.json'

interface Pick {
  icon: string | null
  file: string | null
  annotation: string | null
  reason: string
  latency_s: number
}

interface Draw {
  file: string | null
  parsed: boolean
  sanitised_changed: boolean | null
  latency_s: number
  attempts: unknown[]
}

interface SpikeProduct {
  name: string
  category: string
  category_icon: string
  pick?: Pick
  draw?: Draw
}

const products: SpikeProduct[] = results.products

type Theme = 'light' | 'dark'

const TILE =
  'flex h-20 w-20 flex-col items-center justify-center rounded-2xl border-2 ' +
  'border-green-500 bg-green-100 dark:border-green-400 dark:bg-green-950'

function Icon({ src, emoji, size }: { src?: string | null; emoji?: string; size: number }) {
  if (src) {
    return (
      // A plain <img>: the SVG must load as an image, never be inlined (see the file comment).
      // eslint-disable-next-line @next/next/no-img-element
      <img src={src} alt="" width={size} height={size} style={{ width: size, height: size }} />
    )
  }
  if (emoji) {
    return (
      <span aria-hidden="true" style={{ fontSize: size * 0.8, lineHeight: `${size}px` }}>
        {emoji}
      </span>
    )
  }
  return (
    <span
      className="flex items-center justify-center text-xs text-ui-text-secondary dark:text-ui-dark-text-secondary"
      style={{ width: size, height: size }}
    >
      none
    </span>
  )
}

function Cell({
  label,
  caption,
  src,
  emoji,
}: {
  label: string
  caption: string
  src?: string | null
  emoji?: string
}) {
  return (
    <figure className="flex flex-col items-center gap-2">
      <figcaption className="text-xs font-semibold uppercase tracking-wide text-ui-text dark:text-ui-dark-text">
        {label}
      </figcaption>
      <div className="flex items-end gap-3">
        <div className={TILE}>
          <Icon src={src} emoji={emoji} size={40} />
        </div>
        <Icon src={src} emoji={emoji} size={96} />
      </div>
      <p className="max-w-[12rem] text-center text-xs text-ui-text-secondary dark:text-ui-dark-text-secondary">
        {caption}
      </p>
    </figure>
  )
}

function Panel({ product, theme }: { product: SpikeProduct; theme: Theme }) {
  const pick = product.pick
  const draw = product.draw
  return (
    <div className={theme}>
      <div className="flex flex-wrap justify-around gap-4 rounded-ui-lg bg-ui-bg p-4 dark:bg-ui-dark-bg">
        <Cell label="Today" caption={`category: ${product.category}`} emoji={product.category_icon} />
        <Cell
          label="(a) picked"
          caption={
            pick
              ? `${pick.annotation ?? 'null'} · ${pick.latency_s} s`
              : 'not run'
          }
          src={pick?.file}
        />
        <Cell
          label="(b) drawn"
          caption={
            draw
              ? draw.file
                ? `${draw.attempts.length} attempt(s) · ${draw.latency_s} s` +
                  (draw.sanitised_changed ? ' · sanitised' : '')
                : `failed · ${draw.latency_s} s`
              : 'not run'
          }
          src={draw?.file}
        />
      </div>
    </div>
  )
}

export default function IconSpikePage() {
  return (
    <main className="min-h-screen bg-ui-bg-secondary p-6 dark:bg-ui-dark-bg">
      <div className="mx-auto max-w-7xl space-y-6">
        <header className="space-y-1">
          <h1 className="text-3xl font-bold text-ui-text dark:text-ui-dark-text">
            Product icons: picked or drawn (Q18 spike)
          </h1>
          <p className="text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary">
            Today&apos;s category emoji, (a) an OpenMoji icon the model picked and (b) a flat SVG the
            model drew, at tile size and 96 px, light and dark. Findings:
            docs/spikes/Q18_product_icons.md. OpenMoji icons are CC BY-SA 4.0 (openmoji.org).
          </p>
        </header>
        {products.map((product) => (
          <section
            key={product.name}
            data-testid="icon-row"
            className="space-y-3 rounded-ui-lg border border-ui-border bg-ui-bg p-4 dark:border-ui-dark-border dark:bg-ui-dark-bg-secondary"
          >
            <h2 className="text-lg font-semibold text-ui-text dark:text-ui-dark-text">
              {product.name}
            </h2>
            <div className="grid gap-3 lg:grid-cols-2">
              <Panel product={product} theme="light" />
              <Panel product={product} theme="dark" />
            </div>
          </section>
        ))}
      </div>
    </main>
  )
}
