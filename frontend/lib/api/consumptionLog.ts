/**
 * Consumption history API (H46)
 * What happened to the food: eaten, thrown away, brought back or corrected, newest first.
 */

import apiClient from './client'
import type {
  ConsumptionLogEntry,
  ConsumptionLogParams,
  ConsumptionSummary,
} from '@/types/consumption'

export async function list(params?: ConsumptionLogParams): Promise<ConsumptionLogEntry[]> {
  return apiClient.get<ConsumptionLogEntry[]>('/consumption-log', { ...params })
}

/** What happened in a window, per action: how many times and how much of each unit. */
export async function summary(params?: {
  since?: string
  until?: string
}): Promise<ConsumptionSummary> {
  return apiClient.get<ConsumptionSummary>('/consumption-log/summary', { ...params })
}

const consumptionLogAPI = { list, summary }

export default consumptionLogAPI
