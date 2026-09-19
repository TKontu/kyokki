import apiClient from './client'
import type {
  CatalogEstimateResponse,
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

/**
 * Ask the model what the catalog's guessed shelf lives should be (Q11).
 *
 * Only products whose shelf life is still a category placeholder are candidates; a
 * number the cook set is never sent. `apply` defaults to false, so the first call
 * proposes and a second one writes.
 */
export async function estimate(apply = false): Promise<CatalogEstimateResponse> {
  return apiClient.post<CatalogEstimateResponse>(
    `/products/estimate?apply=${apply}`,
    {}
  )
}

const productsAPI = { list, get, update, estimate }
export default productsAPI
