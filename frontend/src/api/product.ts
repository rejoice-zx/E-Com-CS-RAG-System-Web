import request from '@/utils/request'
import type { 
  Product, 
  PaginatedResponse,
  CreateProductRequest,
  UpdateProductRequest
} from '@/types'

export function getProducts(params: {
  page?: number
  page_size?: number
  category?: string
  min_price?: number
  max_price?: number
  in_stock?: boolean
}) {
  return request.get<PaginatedResponse<Product>>('/products', { params })
}

export function createProduct(data: CreateProductRequest) {
  return request.post<Product>('/products', data)
}

export function updateProduct(id: string, data: UpdateProductRequest) {
  return request.put<Product>(`/products/${id}`, data)
}

export function deleteProduct(id: string) {
  return request.delete(`/products/${id}`)
}

export function deleteProductsByCategory(category: string) {
  return request.delete<{ deleted_count: number; category: string }>(`/products/by-category/${encodeURIComponent(category)}`)
}

export function importProducts(data: Product[], skipDuplicates = true) {
  return request.post('/products/import', { items: data, skip_duplicates: skipDuplicates })
}

export function exportProducts() {
  return request.get<{ items: Product[]; total: number }>('/products/export/all')
}

/**
 * 同步所有商品到知识库（SSE 流式）
 * 返回一个 ReadableStream reader，调用方逐行解析 SSE 事件
 */
export async function syncAllProductsToKnowledgeSSE(): Promise<ReadableStreamDefaultReader<Uint8Array>> {
  const token = localStorage.getItem('token') || ''
  const resp = await fetch('/api/products/sync-knowledge', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
  })
  if (!resp.ok) {
    throw new Error(`同步请求失败: ${resp.status}`)
  }
  return resp.body!.getReader()
}

export function getProductCategories() {
  return request.get<{ categories: string[] }>('/products/categories/list')
}
