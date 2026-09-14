import apiClient from './client'
import type { Category } from '@/types/category'

export async function list(): Promise<Category[]> {
  return apiClient.get<Category[]>('/categories')
}

const categoriesAPI = { list }
export default categoriesAPI
