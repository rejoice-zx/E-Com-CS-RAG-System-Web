import request from '@/utils/request'
import type { 
  KnowledgeItem, 
  PaginatedResponse,
  CreateKnowledgeRequest,
  UpdateKnowledgeRequest,
  IndexStatus
} from '@/types'

export function getKnowledgeList(params: {
  page?: number
  page_size?: number
  category?: string
  keyword?: string
}) {
  return request.get<PaginatedResponse<KnowledgeItem>>('/knowledge', { params })
}

export function getKnowledge(id: string) {
  return request.get<KnowledgeItem>(`/knowledge/${id}`)
}

export function createKnowledge(data: CreateKnowledgeRequest) {
  return request.post<KnowledgeItem>('/knowledge', data)
}

export function updateKnowledge(id: string, data: UpdateKnowledgeRequest) {
  return request.put<KnowledgeItem>(`/knowledge/${id}`, data)
}

export function deleteKnowledge(id: string) {
  return request.delete(`/knowledge/${id}`)
}

export function deleteKnowledgeByCategory(category: string) {
  return request.delete<{ deleted_count: number; category: string }>(`/knowledge/by-category/${encodeURIComponent(category)}`)
}

export function importKnowledge(data: KnowledgeItem[], skipDuplicates = true) {
  return request.post('/knowledge/import', { items: data, skip_duplicates: skipDuplicates })
}

export function exportKnowledge() {
  return request.get<{ items: KnowledgeItem[]; total: number }>('/knowledge/export/all')
}

export function rebuildIndex() {
  return request.post('/knowledge/index/rebuild')
}

/**
 * 重建向量索引（SSE 流式进度）
 */
export async function rebuildIndexSSE(): Promise<ReadableStreamDefaultReader<Uint8Array>> {
  const token = localStorage.getItem('token') || ''
  const resp = await fetch('/api/knowledge/index/rebuild', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
  })
  if (!resp.ok) {
    throw new Error(`重建请求失败: ${resp.status}`)
  }
  return resp.body!.getReader()
}

export function getIndexStatus() {
  return request.get<IndexStatus>('/knowledge/index/status')
}

export function getKnowledgeCategories() {
  return request.get<{ categories: string[] }>('/knowledge/categories/list')
}
