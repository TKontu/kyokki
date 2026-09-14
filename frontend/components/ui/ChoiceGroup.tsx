'use client'

import React from 'react'

export interface ChoiceOption<T extends string> {
  value: T
  label: React.ReactNode
}

export interface ChoiceGroupProps<T extends string> {
  /** Accessible name of the group, e.g. "Location". */
  label: string
  /** Shared radio input name. */
  name: string
  options: ChoiceOption<T>[]
  value: T | null
  onChange: (value: T) => void
  /** Grid classes for the buttons, e.g. "grid-cols-3". */
  className?: string
}

/** One tappable button-like radio. */
export function Choice({
  name,
  checked,
  onChange,
  children,
}: {
  name: string
  checked: boolean
  onChange: () => void
  children: React.ReactNode
}) {
  return (
    // `relative` keeps the visually hidden input inside its label; without it the input is
    // positioned against an ancestor and taps or focus can land on the wrong choice.
    <label
      className={`relative flex min-h-touch cursor-pointer items-center justify-center rounded-ui border px-3 text-sm ${
        checked
          ? 'border-ui-text bg-ui-text text-white dark:border-ui-dark-text dark:bg-ui-dark-text dark:text-ui-dark-bg'
          : 'border-ui-border text-ui-text dark:border-ui-dark-border dark:text-ui-dark-text'
      }`}
    >
      <input type="radio" name={name} className="sr-only" checked={checked} onChange={onChange} />
      {children}
    </label>
  )
}

/** A segmented single choice (units, locations, categories) built from real radio inputs. */
export function ChoiceGroup<T extends string>({
  label,
  name,
  options,
  value,
  onChange,
  className = 'grid-cols-3',
}: ChoiceGroupProps<T>) {
  return (
    <div role="radiogroup" aria-label={label} className={`grid gap-2 ${className}`}>
      {options.map((option) => (
        <Choice
          key={option.value}
          name={name}
          checked={value === option.value}
          onChange={() => onChange(option.value)}
        >
          {option.label}
        </Choice>
      ))}
    </div>
  )
}

export default ChoiceGroup
