/**
 * Consumption history API (H46)
 * What happened to the food: eaten, thrown away, brought back or corrected, newest first.
 */

import apiClient from './client'
import type { ConsumptionLogEntry, ConsumptionLogParams } from '@/types/consumption'

export async function list(params?: ConsumptionLogParams): Promise<ConsumptionLogEntry[]> {
  return apiClient.get<ConsumptionLogEntry[]>('/consumption-log', { ...params })
}

const consumptionLogAPI = { list }

export default consumptionLogAPI
