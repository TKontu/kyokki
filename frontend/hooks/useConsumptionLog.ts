/**
 * useConsumptionLog (H46)
 * The consumption history, read back. Every inventory mutation that moves a quantity writes a
 * row, so those mutations invalidate `consumptionLogKeys.all`.
 */

import { useQuery } from '@tanstack/react-query'
import consumptionLogAPI from '@/lib/api/consumptionLog'
import type {
  ConsumptionLogEntry,
  ConsumptionLogParams,
  ConsumptionSummary,
} from '@/types/consumption'

export const consumptionLogKeys = {
  all: ['consumption-log'] as const,
  lists: () => [...consumptionLogKeys.all, 'list'] as const,
  list: (params?: ConsumptionLogParams) => [...consumptionLogKeys.lists(), params] as const,
  summaries: () => [...consumptionLogKeys.all, 'summary'] as const,
  summary: (params?: SummaryParams) => [...consumptionLogKeys.summaries(), params] as const,
}

export interface SummaryParams {
  since?: string
  until?: string
}

/** A page of the history, newest first; `{ action: ['discard'] }` is the waste. */
export function useConsumptionLog(params?: ConsumptionLogParams) {
  return useQuery<ConsumptionLogEntry[]>({
    queryKey: consumptionLogKeys.list(params),
    queryFn: () => consumptionLogAPI.list(params),
  })
}

/**
 * What a window cost, per action. A count over a month would otherwise mean paging the whole
 * month into the browser to add it up.
 */
export function useConsumptionSummary(params?: SummaryParams) {
  return useQuery<ConsumptionSummary>({
    queryKey: consumptionLogKeys.summary(params),
    queryFn: () => consumptionLogAPI.summary(params),
  })
}
