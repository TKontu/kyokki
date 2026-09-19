import apiClient from './client'
import type {
  ProductListParams,
  ProductMaster,
  ProductMasterUpdate,
} from '@/types/product'

export async function list(params?: ProductListParams): Promise<ProductMaster[]> {
  return apiClient.get<ProductMaster[]>('/products', params as Record<string, string | undefined>)
}

export async function get(id: string): Promise<ProductMaster> {
  return apiClient.get<ProductMaster>(`/products/${id}`)
}

/**
 * Correct what the catalog believes about a product (H18).
 *
 * `unit_type` is derived server-side from `default_unit`, so it is never sent: the
 * backend canonicalises the unit and works the type out from it.
 */
export async function update(
  id: string,
  data: ProductMasterUpdate
): Promise<ProductMaster> {
  return apiClient.patch<ProductMaster>(`/products/${id}`, data)
}

const productsAPI = { list, get, update }
export default productsAPI
