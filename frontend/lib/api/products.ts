import apiClient from './client'
import type {
  CatalogEstimateResponse,
  ProductListParams,
  ProductMaster,
  ProductMasterUpdate,
  ProductNames,
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
 * Which products a catalog estimate asks about (Q19). `guesses`: only category
 * placeholders (Q11). `all`: every product whose shelf life the cook did not set.
 */
export type EstimateScope = 'guesses' | 'all'

/**
 * Ask the model what the catalog's shelf lives should be (Q11, Q19).
 *
 * A number the cook set is never sent, in either scope. `apply` defaults to false, so
 * the first call proposes and a second one writes.
 */
export async function estimate(
  apply = false,
  scope: EstimateScope = 'guesses'
): Promise<CatalogEstimateResponse> {
  return apiClient.post<CatalogEstimateResponse>(
    `/products/estimate?apply=${apply}&scope=${scope}`,
    {}
  )
}

/** The names and printed receipt names that resolve to a product (H52). */
export async function names(id: string): Promise<ProductNames> {
  return apiClient.get<ProductNames>(`/products/${id}/names`)
}

/** Stop a learned name meaning this product. The canonical name answers 409. */
export async function forgetName(id: string, nameId: string): Promise<void> {
  return apiClient.delete<void>(`/products/${id}/names/${nameId}`)
}

/** Stop a printed receipt name resolving to this product. */
export async function forgetPrintedName(id: string, aliasId: string): Promise<void> {
  return apiClient.delete<void>(`/products/${id}/aliases/${aliasId}`)
}

const productsAPI = { list, get, update, estimate, names, forgetName, forgetPrintedName }
export default productsAPI
