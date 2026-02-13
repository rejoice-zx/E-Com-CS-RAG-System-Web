import request from '@/utils/request'

interface PendingConversationSummary {
  id: string
  title: string
  status: string
  updated_at: string
  message_count?: number
  wait_time_seconds?: number
}

interface PendingConversationListResponse {
  items: PendingConversationSummary[]
  total: number
  page: number
  page_size: number
}

interface HumanMessageResponse {
  id: number
  conversation_id: string
  role: string
  content: string
  timestamp: string
}

export function getPendingConversations() {
  return request.get<PendingConversationListResponse>('/human/pending')
}

export function getHandlingConversations() {
  return request.get('/human/handling')
}

export function acceptConversation(conversationId: string) {
  return request.post(`/human/accept/${conversationId}`)
}

export function closeConversation(conversationId: string) {
  return request.post(`/human/close/${conversationId}`)
}

export function sendHumanMessage(conversationId: string, content: string) {
  return request.post<HumanMessageResponse>(`/human/${conversationId}/messages`, { content })
}

export function cancelTransfer(conversationId: string) {
  return request.post(`/human/cancel/${conversationId}`)
}

export function returnToAI(conversationId: string) {
  return request.post(`/human/return-ai/${conversationId}`)
}
