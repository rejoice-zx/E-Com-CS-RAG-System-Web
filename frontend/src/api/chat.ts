import request from '@/utils/request'
import type { 
  Conversation, 
  Message, 
  PaginatedResponse,
  SendMessageRequest 
} from '@/types'

export function createConversation() {
  return request.post<Conversation>('/chat/conversations')
}

export function getConversations(params: {
  page?: number
  page_size?: number
  status?: string
} = {}) {
  return request.get<PaginatedResponse<Conversation>>('/chat/conversations', { params })
}

export function getConversation(id: string) {
  return request.get<Conversation>(`/chat/conversations/${id}`)
}

export function deleteConversation(id: string) {
  return request.delete(`/chat/conversations/${id}`)
}

export function updateConversation(id: string, data: { title?: string; status?: string }) {
  return request.put<Conversation>(`/chat/conversations/${id}`, data)
}

export function getMessages(conversationId: string, params: {
  page?: number
  page_size?: number
  include_deleted?: boolean
  since_id?: number
} = {}) {
  return request.get<PaginatedResponse<Message>>(`/chat/conversations/${conversationId}/messages`, { params })
}

export function deleteMessage(conversationId: string, messageId: number, hard = false) {
  return request.delete(`/chat/conversations/${conversationId}/messages/${messageId}`, {
    params: { hard }
  })
}

export function sendMessage(conversationId: string, data: SendMessageRequest, stream = true) {
  if (stream) {
    // For streaming, return the URL for EventSource
    return request.post(`/chat/conversations/${conversationId}/messages`, data, {
      params: { stream: true }
    })
  }
  return request.post<Message>(`/chat/conversations/${conversationId}/messages`, data, {
    params: { stream: false }
  })
}

export function transferToHuman(conversationId: string, reason?: string) {
  return request.post(`/chat/conversations/${conversationId}/transfer-human`, { reason })
}

export function debugRAG(query: string) {
  return request.post('/chat/debug-rag', { query })
}

export function countMessagesByDateRange(params: { before?: string; after?: string }) {
  return request.get<{ count: number }>('/chat/messages/count-by-date', { params })
}

export function batchDeleteMessagesByDate(params: { before?: string; after?: string }) {
  return request.delete<{ deleted_count: number; message: string }>('/chat/messages/batch-by-date', { params })
}
