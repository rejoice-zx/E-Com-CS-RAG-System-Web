import request from '@/utils/request'
import type { LogEntry, PaginatedResponse } from '@/types'

export function getLogs(params: {
  page?: number
  page_size?: number
  level?: string
  start_time?: string
  end_time?: string
  keyword?: string
}) {
  return request.get<PaginatedResponse<LogEntry>>('/logs', { params })
}

export function downloadLogs(logType: 'app' | 'error') {
  return request.get(`/logs/download`, {
    params: { log_type: logType },
    responseType: 'blob'
  })
}

export function clearLogs(logType: 'app' | 'error') {
  return request.post('/logs/clear', { log_type: logType })
}
