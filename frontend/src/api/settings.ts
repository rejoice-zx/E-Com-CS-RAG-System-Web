import request from '@/utils/request'
import type { SystemSettings, LLMProvider, TestConnectionResult } from '@/types'

export function getSettings() {
  return request.get<SystemSettings>('/settings')
}

export function updateSettings(data: Partial<SystemSettings>) {
  return request.put<SystemSettings>('/settings', data)
}

export function getLLMProviders() {
  return request.get<LLMProvider[]>('/settings/llm-providers')
}

export function testConnection(data: { 
  provider: string
  api_key: string
  api_url?: string
  model?: string 
}) {
  return request.post<TestConnectionResult>('/settings/test-connection', data)
}
