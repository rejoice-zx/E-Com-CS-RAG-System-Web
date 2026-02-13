// User types
export interface User {
  id: number
  username: string
  role: 'admin' | 'cs' | 'customer'
  displayName: string
  email?: string
  isActive: boolean
  createdAt?: string
  lastLogin?: string
}

// Auth types
export interface LoginRequest {
  username: string
  password: string
  visitor_id?: string
  guest_device_id?: string
  guest_conversation_ids?: string[]
}

export interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
  user: User
}

export interface RegisterRequest {
  username: string
  password: string
  display_name: string
  email?: string
}

export interface CustomerRegisterRequest {
  username: string
  password: string
  display_name: string
  visitor_id?: string
  guest_device_id?: string
  guest_conversation_ids?: string[]
}

// Conversation types
export type ConversationStatus = 'normal' | 'pending_human' | 'human_handling' | 'human_closed'

export interface Conversation {
  id: string
  title: string
  status: ConversationStatus
  customer_id?: string
  humanAgentId?: number
  createdAt: string
  updatedAt: string
  updated_at?: string
  messageCount?: number
}

// Message types
export type MessageRole = 'user' | 'assistant' | 'human'

export interface RAGTrace {
  query: string
  rewritten_query: string
  retrieved_items: Array<{
    id: string
    question: string
    score: number
  }>
  context_text: string
  confidence: number
  search_method: 'vector' | 'keyword'
  final_prompt?: string
}

export interface Message {
  id: number
  conversationId: string
  conversation_id?: string
  role: MessageRole
  content: string
  confidence?: number
  ragTrace?: RAGTrace
  rag_trace?: RAGTrace
  human_agent_name?: string
  is_deleted_by_user?: boolean
  deleted_by_customer_id?: string
  deleted_at?: string
  timestamp: string
  /** 标记为前端临时消息（ID 为负数），不参与 since_id 计算 */
  _isTemp?: boolean
}

export interface SendMessageRequest {
  content: string
}

// Knowledge types
export interface KnowledgeItem {
  id: string
  question: string
  answer: string
  keywords: string[]
  category: string
  score: number
  createdAt?: string
  updatedAt?: string
}

export interface CreateKnowledgeRequest {
  question: string
  answer: string
  keywords: string[]
  category: string
}

export interface UpdateKnowledgeRequest {
  question?: string
  answer?: string
  keywords?: string[]
  category?: string
}

export interface IndexStatus {
  dimension: number
  count: number
  embeddingModel: string
  lastUpdated?: string
}

// Product types
export interface Product {
  id: string
  name: string
  price: number
  category: string
  description: string
  specifications: Record<string, string>
  stock: number
  keywords: string[]
  createdAt?: string
  updatedAt?: string
}

export interface CreateProductRequest {
  name: string
  price: number
  category: string
  description: string
  specifications: Record<string, string>
  stock: number
  keywords: string[]
}

export interface UpdateProductRequest {
  name?: string
  price?: number
  category?: string
  description?: string
  specifications?: Record<string, string>
  stock?: number
  keywords?: string[]
}

// Statistics types
export interface StatisticsOverview {
  totalConversations: number
  totalMessages: number
  totalKnowledgeItems: number
  totalProducts: number
  totalUsers: number
  conversationsToday: number
  conversationsThisWeek: number
  conversationsThisMonth: number
  avgResponseTime: number
  successRate: number
}

export interface DailyStatistics {
  date: string
  conversations: number
  messages: number
  userMessages: number
  assistantMessages: number
}

export interface CategoryDistribution {
  knowledge: Record<string, number>
  products: Record<string, number>
}

// Performance types
export interface PerformanceSummary {
  uptime_seconds: number
  uptime_formatted: string
  total_requests: number
  overall_success_rate: number
  start_time: string
}

export interface MetricStatsData {
  name: string
  count: number
  success_rate: number
  avg_duration: number
  min_duration: number
  max_duration: number
  p50_duration: number
  p95_duration: number
  p99_duration: number
  total_count: number
  total_success: number
}

export interface PerformanceMetrics {
  summary: PerformanceSummary
  metrics: Record<string, MetricStatsData>
}

// Log types
export type LogLevel = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL'

export interface LogEntry {
  timestamp: string
  level: LogLevel
  message: string
  source?: string
}

// Settings types
export interface SystemSettings {
  llmProvider: string
  llmApiKey?: string
  llmApiUrl?: string
  llmModel?: string
  ragTopK: number
  ragSimilarityThreshold: number
  ragUseKeywordSearch: boolean
  // Allow additional properties for API compatibility
  llm?: {
    provider?: string
    api_key?: string
    api_url?: string
    model?: string
    has_api_key?: boolean
  }
  rag?: {
    top_k?: number
    similarity_threshold?: number
    use_rewrite?: boolean
    max_context_length?: number
  }
  general?: {
    timezone?: string
  }
}

export interface LLMProvider {
  id: string
  name: string
  models: string[]
  requiresApiKey: boolean
  defaultApiUrl?: string
}

export interface TestConnectionResult {
  success: boolean
  message: string
  latency?: number
}

// RAG Config type
export interface RAGConfig {
  topK: number
  similarityThreshold: number
  useKeywordSearch: boolean
}

// API Response types
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface ApiError {
  detail: string
}
