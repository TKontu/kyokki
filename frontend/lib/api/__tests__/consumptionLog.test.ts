/**
 * Consumption history API module (H46). Fetch mocks, like receipts.test.ts.
 */

import consumptionLogAPI from '../consumptionLog'
import type { ConsumptionLogEntry } from '@/types/consumption'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api'

const entry: ConsumptionLogEntry = {
  id: 'l1',
  inventory_item_id: 'i1',
  product_master_id: 'p1',
  product_name: 'Milk',
  unit: 'dl',
  action: 'discard',
  quantity_consumed: 4,
  quantity_after: 0,
  logged_at: '2026-09-22T08:00:00+00:00',
}

global.fetch = jest.fn()

function respond(body: unknown, status = 200) {
  ;(global.fetch as jest.Mock).mockResolvedValueOnce({
    ok: status < 400,
    status,
    statusText: 'OK',
    json: async () => body,
  })
}

function lastUrl(): string {
  return (global.fetch as jest.Mock).mock.calls.at(-1)[0]
}

beforeEach(() => (global.fetch as jest.Mock).mockReset())

describe('consumption log API', () => {
  it('reads the whole history without params', async () => {
    respond([entry])

    await expect(consumptionLogAPI.list()).resolves.toEqual([entry])
    expect(lastUrl()).toBe(`${API_URL}/consumption-log`)
  })

  it('sends several actions as a repeated parameter', async () => {
    respond([])

    await consumptionLogAPI.list({ action: ['discard', 'use_full'], limit: 20 })

    expect(lastUrl()).toBe(`${API_URL}/consumption-log?action=discard&action=use_full&limit=20`)
  })

  it('narrows to one item', async () => {
    respond([])

    await consumptionLogAPI.list({ inventory_item_id: 'i1' })

    expect(lastUrl()).toBe(`${API_URL}/consumption-log?inventory_item_id=i1`)
  })
})
