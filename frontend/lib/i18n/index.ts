/**
 * The app's own UI text, translated (Post-MVP frontier item 13, phase 2).
 *
 * `en.ts` is the source of keys; `fi.ts` is typed against it (`Messages`), so a key `fi.ts`
 * does not have - or has in the wrong shape - fails `tsc`. Phase 1 (#162) already covers a
 * product's own name (`lib/displayName.ts`) and never goes through this: that is
 * `display_names`, cook-set or model-proposed per product, not app chrome, and receipt text
 * (the printed line) goes through neither.
 *
 * `useT()` follows `lib/language.ts`'s stored choice and re-renders on a later change -
 * this tab's own Settings toggle, or another tab's - the same reactivity `useLanguage` itself
 * now has, since both read the same `subscribeToLanguage`.
 */

'use client'

import { useCallback } from 'react'
import { en, type Messages } from './en'
import { fi } from './fi'
import { useLanguage, type Language } from '@/lib/language'

const CATALOGUES: Record<Language, Messages> = { en, fi }

export type TranslateParams = Record<string, string | number>

/** One / other, by Finnish numeral agreement (see `fi.ts`'s own docstring): exactly one count
 * takes `one`, anything else - including zero - takes `other`. */
export interface PluralForms {
  one: string
  other: string
}

function isPluralForms(value: unknown): value is PluralForms {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as PluralForms).one === 'string' &&
    typeof (value as PluralForms).other === 'string'
  )
}

/** `{name}` -> `params.name`; a placeholder with nothing supplied is left as-is rather than
 * silently blanked, so a missing param is visible instead of hidden. */
function interpolate(template: string, params?: TranslateParams): string {
  if (!params) return template
  return template.replace(/\{(\w+)\}/g, (match, key: string) =>
    key in params ? String(params[key]) : match
  )
}

/** A dotted key ("shopping.itemRow.remove") into the catalogue; the key itself if any step is
 * missing - a typo surfaces as literal text on screen rather than a thrown error on an
 * always-on display nobody is standing at to see a stack trace. */
function lookup(catalogue: Messages, key: string): string | PluralForms | undefined {
  const parts = key.split('.')
  let node: unknown = catalogue
  for (const part of parts) {
    if (typeof node !== 'object' || node === null) return undefined
    node = (node as Record<string, unknown>)[part]
  }
  return typeof node === 'string' || isPluralForms(node) ? node : undefined
}

/**
 * Resolves one key in `catalogue`, falling back to `en` (never to the bare key) when the
 * language's own catalogue is missing it - `fi.ts` being `tsc`-checked against `en.ts` means
 * this fallback is theoretical for a key that compiles, not a crutch load-bearing in practice.
 * `params.count`, when present, picks a plural pair's form; every placeholder then
 * interpolates from `params`.
 */
function resolve(catalogue: Messages, key: string, params?: TranslateParams): string {
  const node = lookup(catalogue, key) ?? lookup(en, key) ?? key
  if (typeof node === 'string') return interpolate(node, params)
  const count = typeof params?.count === 'number' ? params.count : Number(params?.count)
  const form = count === 1 ? node.one : node.other
  return interpolate(form, params)
}

/**
 * The current language, and `t(key, params)` to read one message in it. Re-renders whenever
 * the stored language changes - this component's own setter, a sibling's, or another tab's -
 * without needing a fresh mount (see the module docstring).
 */
export function useT(): { t: (key: string, params?: TranslateParams) => string; language: Language } {
  const [language] = useLanguage()
  const catalogue = CATALOGUES[language]
  const t = useCallback(
    (key: string, params?: TranslateParams) => resolve(catalogue, key, params),
    [catalogue]
  )
  return { t, language }
}

export type { Messages } from './en'

/** The `Intl` locale for a language choice: British English stands in for "English" the same
 * way `lib/gone.ts` and `lib/dates.ts` already format dates (`toLocaleDateString('en-GB', …)`)
 * - a day-month-year order, not the US one - and Finnish is simply its own locale. */
const LOCALES: Record<Language, string> = { en: 'en-GB', fi: 'fi-FI' }

export function localeFor(language: Language): string {
  return LOCALES[language]
}

/** A whole number or a decimal amount (a shopping quantity, a generated line's `need`), in the
 * chosen locale - `fi-FI` reads 2.5 as "2,5", a comma rather than a point. */
export function formatNumber(value: number, language: Language): string {
  return new Intl.NumberFormat(localeFor(language)).format(value)
}

/** A plain `YYYY-MM-DD` (or a full ISO datetime) date, in the chosen locale, day-month-year
 * either way - "3 October 2026" in English, "3. lokakuuta 2026" in Finnish. */
export function formatDate(value: string, language: Language): string {
  return new Intl.DateTimeFormat(localeFor(language), { dateStyle: 'long' }).format(
    new Date(value)
  )
}
