import apiClient from './client'
import type { ProductMaster, ProductListParams } from '@/types/product'

export async function list(params?: ProductListParams): Promise<ProductMaster[]> {
  return apiClient.get<ProductMaster[]>('/products', params as Record<string, string | undefined>)
}

const productsAPI = { list }
export default productsAPI
