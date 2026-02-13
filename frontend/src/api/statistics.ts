import request from '@/utils/request'
import type { 
  StatisticsOverview, 
  DailyStatistics, 
  CategoryDistribution 
} from '@/types'

interface OverviewResponse {
  total_conversations: number
  total_messages: number
  total_knowledge_items: number
  total_products: number
  total_users: number
  conversations_today: number
  conversations_this_week: number
  conversations_this_month: number
  avg_response_time_ms: number
  success_rate: number
}

interface DailyStatsResponse {
  items: Array<{
    date: string
    conversations: number
    messages: number
    user_messages: number
    assistant_messages: number
  }>
  days: number
}

interface CategoryResponse {
  knowledge_categories: Record<string, number>
  product_categories: Record<string, number>
}

export type StatisticsDeleteMode = 'reset_all' | 'date_range'

interface DeleteStatisticsResponse {
  success: boolean
  mode: StatisticsDeleteMode
  deleted_days: number
  deleted_conversations: number
  deleted_messages: number
  message: string
}

export async function getStatisticsOverview() {
  const response = await request.get<OverviewResponse>('/statistics/overview')
  // Transform to frontend format
  return {
    data: {
      totalConversations: response.data.total_conversations,
      totalMessages: response.data.total_messages,
      totalKnowledgeItems: response.data.total_knowledge_items,
      totalProducts: response.data.total_products,
      totalUsers: response.data.total_users,
      conversationsToday: response.data.conversations_today,
      conversationsThisWeek: response.data.conversations_this_week,
      conversationsThisMonth: response.data.conversations_this_month,
      avgResponseTime: response.data.avg_response_time_ms,
      successRate: response.data.success_rate
    } as StatisticsOverview
  }
}

export async function getDailyStatistics(params: {
  start_date?: string
  end_date?: string
}) {
  const response = await request.get<DailyStatsResponse>('/statistics/daily', { params })
  // Transform to frontend format
  return {
    data: response.data.items.map(item => ({
      date: item.date,
      conversations: item.conversations,
      messages: item.messages,
      userMessages: item.user_messages,
      assistantMessages: item.assistant_messages
    })) as DailyStatistics[]
  }
}

export async function getCategoryDistribution() {
  const response = await request.get<CategoryResponse>('/statistics/categories')
  // Transform to frontend format
  return {
    data: {
      knowledge: response.data.knowledge_categories,
      products: response.data.product_categories
    } as CategoryDistribution
  }
}

export function exportStatisticsReport() {
  return request.get<{ content: string; generated_at: string }>('/statistics/export')
}

export function deleteStatisticsData(data: {
  mode: StatisticsDeleteMode
  start_date?: string
  end_date?: string
}) {
  return request.post<DeleteStatisticsResponse>('/statistics/data/delete', data)
}
