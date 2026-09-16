/**
 * Receipt API module (MVP-R5). Fetch mocks, like inventory.test.ts.
 */

import receiptsAPI from '../receipts'
import type { Receipt } from '@/types/receipt'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api'

const receipt = { id: 'r1', processing_status: 'completed', items: [] } as unknown as Receipt

global.fetch = jest.fn()

function respond(body: unknown, status = 200) {
  ;(global.fetch as jest.Mock).mockResolvedValueOnce({
    ok: status < 400,
    status,
    statusText: 'OK',
    json: async () => body,
  })
}

function lastCall() {
  const [url, init] = (global.fetch as jest.Mock).mock.calls.at(-1)
  return { url, method: init?.method, body: init?.body ? JSON.parse(init.body) : undefined }
}

beforeEach(() => (global.fetch as jest.Mock).mockReset())

describe('receipts API', () => {
  it('lists receipts and passes a status filter', async () => {
    respond([receipt])

    await expect(receiptsAPI.list({ status: 'completed' })).resolves.toEqual([receipt])
    expect(lastCall().url).toBe(`${API_URL}/receipts?status=completed`)
  })

  it('lists every receipt without params', async () => {
    respond([])

    await receiptsAPI.list()

    expect(lastCall().url).toBe(`${API_URL}/receipts`)
  })

  it('gets one receipt', async () => {
    respond(receipt)

    await expect(receiptsAPI.get('r1')).resolves.toEqual(receipt)
    expect(lastCall().url).toBe(`${API_URL}/receipts/r1`)
  })

  it('confirms the reviewed items', async () => {
    respond({ success: true, items_created: 2, products_created: 1, aliases_learned: 2 })
    const request = {
      items: [
        { index: 0, product_id: 'p1', quantity: 2, unit: 'pcs', purchase_date: '2026-09-02' },
        { index: 1, name: 'Milk', category: 'dairy', quantity: 10, unit: 'dl', purchase_date: '2026-09-02' },
      ],
    }

    const result = await receiptsAPI.confirm('r1', request)

    expect(result.items_created).toBe(2)
    const call = lastCall()
    expect(call.url).toBe(`${API_URL}/receipts/r1/confirm`)
    expect(call.method).toBe('POST')
    expect(call.body).toEqual(request)
  })

  it('queues a receipt to be read again', async () => {
    respond({ ...receipt, processing_status: 'queued' })

    await receiptsAPI.process('r1')

    expect(lastCall().url).toBe(`${API_URL}/receipts/r1/process`)
    expect(lastCall().method).toBe('POST')
  })
})
