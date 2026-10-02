/**
 * Consumption history API module (H46). Fetch mocks, like receipts.test.ts.
 */

import consumptionLogAPI from '../consumptionLog'
import type { ConsumptionLogEntry } from '@/types/consumption'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api'

const entry: ConsumptionLogEntry = {
  id: 'l1',
  inventory_item_id: 'i1',
  item_status: 'discarded',
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

describe('waste rate and trend', () => {
  it('reads the waste rate for a window', async () => {
    respond({ discarded: 1, finished: 1, total: 2, rate: 0.5, categories: [] })

    await consumptionLogAPI.waste({ since: '2026-09-01T00:00:00Z' })

    expect(lastUrl()).toBe(
      `${API_URL}/consumption-log/waste?since=2026-09-01T00%3A00%3A00Z`
    )
  })

  it('reads the whole history when no window is given', async () => {
    respond({ discarded: 0, finished: 0, total: 0, rate: null, categories: [] })

    await consumptionLogAPI.waste()

    expect(lastUrl()).toBe(`${API_URL}/consumption-log/waste`)
  })

  it('reads the 8-week trend', async () => {
    respond({ weeks: [] })

    await consumptionLogAPI.wasteTrend()

    expect(lastUrl()).toBe(`${API_URL}/consumption-log/waste/trend`)
  })

  it('can ask for a different number of weeks', async () => {
    respond({ weeks: [] })

    await consumptionLogAPI.wasteTrend({ weeks: 4 })

    expect(lastUrl()).toBe(`${API_URL}/consumption-log/waste/trend?weeks=4`)
  })
})
