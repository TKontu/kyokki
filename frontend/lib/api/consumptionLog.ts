/**
 * Consumption history API (H46)
 * What happened to the food: eaten, thrown away, brought back or corrected, newest first.
 */

import apiClient from './client'
import type {
  ConsumptionLogEntry,
  ConsumptionLogParams,
  ConsumptionSummary,
  WasteStats,
  WasteTrend,
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

/** The waste rate for a window, plus where it is worst (planner ruling, 2026-10-02). */
export async function waste(params?: { since?: string }): Promise<WasteStats> {
  return apiClient.get<WasteStats>('/consumption-log/waste', { ...params })
}

/** The last 8 ISO weeks' waste rate and counts, oldest first. The window filter above does
 * not apply here - the trend always looks back from today. */
export async function wasteTrend(params?: { weeks?: number }): Promise<WasteTrend> {
  return apiClient.get<WasteTrend>('/consumption-log/waste/trend', { ...params })
}

const consumptionLogAPI = { list, summary, waste, wasteTrend }

export default consumptionLogAPI
