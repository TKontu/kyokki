'use client'

/**
 * useFailedActions (H45)
 *
 * What went wrong and can be tried again. A card tap raises no success toast by design, and an
 * error toast is gone in five seconds - on a wall display that nobody is necessarily watching,
 * a failed consume would otherwise leave no trace at all. Inventory mutations deliberately do
 * not retry themselves (a retried consume would eat twice), so the retry belongs here, in a
 * place a cook can see and decide.
 *
 * Fed by the mutation cache rather than by each call site: every mutation in the app already
 * goes through it, and a hook that has to be remembered at each call site will be forgotten.
 */

import { useCallback, useEffect, useState } from 'react'
import { useQueryClient, type Mutation } from '@tanstack/react-query'

/** What a mutation calls itself in the banner: `meta: { label: 'Consume' }`. */
export interface ActionMeta extends Record<string, unknown> {
  label?: string
}

export interface FailedAction {
  id: number
  label: string
  failedAt: number
  /** Run it again, exactly as it was run the first time. */
  retry: () => void
  /** Stop offering it, without running anything. */
  dismiss: () => void
}

const UNNAMED = 'An action'

type AnyMutation = Mutation<unknown, Error, unknown, unknown>

export function useFailedActions(): FailedAction[] {
  const client = useQueryClient()
  const [failed, setFailed] = useState<AnyMutation[]>([])
  const [dismissed, setDismissed] = useState<number[]>([])

  useEffect(() => {
    const refresh = () => {
      const all = client
        .getMutationCache()
        .getAll()
        .filter((mutation) => mutation.state.status === 'error') as AnyMutation[]
      // Newest first: the last thing tapped is the first thing worth offering back. Two taps
      // inside one millisecond are ordered by id, which only ever counts up.
      all.sort(
        (a, b) =>
          b.state.submittedAt - a.state.submittedAt || b.mutationId - a.mutationId
      )
      setFailed(all)
    }
    refresh()
    return client.getMutationCache().subscribe(refresh)
  }, [client])

  const dismiss = useCallback((id: number) => {
    setDismissed((ids) => [...ids, id])
  }, [])

  return failed
    .filter((mutation) => !dismissed.includes(mutation.mutationId))
    .map((mutation) => ({
      id: mutation.mutationId,
      label: (mutation.options.meta as ActionMeta | undefined)?.label ?? UNNAMED,
      failedAt: mutation.state.submittedAt,
      // What `Mutation.continue()` does for a paused mutation, asked for by hand instead. The
      // row clears itself when this lands, because the cache tells us it did.
      retry: () => {
        void mutation.execute(mutation.state.variables).catch(() => undefined)
      },
      dismiss: () => dismiss(mutation.mutationId),
    }))
}
