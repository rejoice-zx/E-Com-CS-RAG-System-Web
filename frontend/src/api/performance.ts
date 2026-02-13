import request from '@/utils/request'
import type { PerformanceSummary, PerformanceMetrics } from '@/types'

export function getPerformanceSummary() {
  return request.get<PerformanceSummary>('/performance/summary')
}

export function getPerformanceMetrics() {
  return request.get<PerformanceMetrics>('/performance/metrics')
}

export function clearPerformanceData() {
  return request.post('/performance/clear')
}

export function exportPerformanceReport() {
  return request.get<string>('/performance/export')
}
