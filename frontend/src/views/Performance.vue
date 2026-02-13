<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Download, Delete, Timer, Odometer } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import {
  getPerformanceSummary,
  getPerformanceMetrics,
  clearPerformanceData,
  exportPerformanceReport
} from '@/api/performance'

// Types
interface MetricStats {
  name: string
  count: number
  successRate: number
  avgDuration: number
  minDuration: number
  maxDuration: number
  p50Duration: number
  p95Duration: number
  p99Duration: number
}

interface PerformanceSummary {
  uptimeSeconds: number
  uptimeFormatted: string
  totalRequests: number
  overallSuccessRate: number
  startTime: string
}

// State
const loading = ref(false)
const summary = ref<PerformanceSummary | null>(null)
const metrics = ref<Record<string, MetricStats>>({})

// ECharts
const barChartRef = ref<HTMLElement | null>(null)
const successChartRef = ref<HTMLElement | null>(null)
let barChartInstance: echarts.ECharts | null = null
let successChartInstance: echarts.ECharts | null = null

// Whether there is any metric data with actual calls
const hasData = computed(() => Object.values(metrics.value).some(m => m.count > 0))

// Get metric display label
function getMetricLabel(key: string): string {
  const labels: Record<string, string> = {
    'chat_api': 'Chat API',
    'embedding_api': 'Embedding',
    'vector_search': '向量检索',
    'keyword_search': '关键词检索',
    'knowledge_add': '知识库添加',
    'knowledge_update': '知识库更新',
    'product_add': '商品添加',
    'product_update': '商品更新'
  }
  return labels[key] || key
}

// Load performance data
async function loadPerformanceData() {
  loading.value = true
  try {
    const [summaryRes, metricsRes] = await Promise.all([
      getPerformanceSummary(),
      getPerformanceMetrics()
    ])

    const data = summaryRes.data as any
    summary.value = {
      uptimeSeconds: data.uptime_seconds || data.uptime || 0,
      uptimeFormatted: data.uptime_formatted || formatUptime(data.uptime_seconds || data.uptime || 0),
      totalRequests: data.total_requests || data.totalRequests || 0,
      overallSuccessRate: data.overall_success_rate || 1,
      startTime: data.start_time || new Date().toISOString()
    }

    const metricsData = metricsRes.data as any
    const transformedMetrics: Record<string, MetricStats> = {}
    for (const [key, value] of Object.entries(metricsData.metrics || metricsData || {})) {
      const v = value as any
      transformedMetrics[key] = {
        name: v.name,
        count: v.count,
        successRate: v.success_rate,
        avgDuration: v.avg_duration,
        minDuration: v.min_duration,
        maxDuration: v.max_duration,
        p50Duration: v.p50_duration,
        p95Duration: v.p95_duration,
        p99Duration: v.p99_duration
      }
    }
    metrics.value = transformedMetrics

    await nextTick()
    renderBarChart()
    renderSuccessChart()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '加载性能数据失败')
  } finally {
    loading.value = false
  }
}

// Render bar chart with ECharts
function renderBarChart() {
  if (!barChartRef.value) return

  if (!barChartInstance) {
    barChartInstance = echarts.init(barChartRef.value)
  }

  const entries = Object.entries(metrics.value).filter(([, m]) => m.count > 0)
  if (entries.length === 0) {
    barChartInstance.clear()
    return
  }

  const categories = entries.map(([k]) => getMetricLabel(k))
  const p50Data = entries.map(([, m]) => +(m.p50Duration * 1000).toFixed(2))
  const p95Data = entries.map(([, m]) => +(m.p95Duration * 1000).toFixed(2))
  const p99Data = entries.map(([, m]) => +(m.p99Duration * 1000).toFixed(2))

  barChartInstance.setOption({
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter(params: any) {
        let html = `<div style="font-weight:600;margin-bottom:4px">${params[0].axisValue}</div>`
        for (const p of params) {
          html += `<div>${p.marker} ${p.seriesName}: <b>${p.value}ms</b></div>`
        }
        return html
      }
    },
    legend: {
      data: ['P50', 'P95', 'P99'],
      top: 0
    },
    grid: { left: 50, right: 20, top: 40, bottom: 40 },
    xAxis: {
      type: 'category',
      data: categories,
      axisLabel: { interval: 0, rotate: entries.length > 5 ? 20 : 0 }
    },
    yAxis: {
      type: 'value',
      name: '耗时 (ms)',
      axisLabel: { formatter: '{value}' }
    },
    series: [
      {
        name: 'P50',
        type: 'bar',
        data: p50Data,
        itemStyle: { color: '#67C23A', borderRadius: [3, 3, 0, 0] },
        barMaxWidth: 36
      },
      {
        name: 'P95',
        type: 'bar',
        data: p95Data,
        itemStyle: { color: '#E6A23C', borderRadius: [3, 3, 0, 0] },
        barMaxWidth: 36
      },
      {
        name: 'P99',
        type: 'bar',
        data: p99Data,
        itemStyle: { color: '#F56C6C', borderRadius: [3, 3, 0, 0] },
        barMaxWidth: 36
      }
    ]
  }, true)
}

// Render success rate gauge / pie chart
function renderSuccessChart() {
  if (!successChartRef.value) return

  if (!successChartInstance) {
    successChartInstance = echarts.init(successChartRef.value)
  }

  const entries = Object.entries(metrics.value).filter(([, m]) => m.count > 0)
  if (entries.length === 0) {
    successChartInstance.clear()
    return
  }

  const categories = entries.map(([k]) => getMetricLabel(k))
  const avgData = entries.map(([, m]) => +(m.avgDuration * 1000).toFixed(2))
  const countData = entries.map(([, m]) => m.count)
  const successData = entries.map(([, m]) => +(m.successRate * 100).toFixed(1))

  successChartInstance.setOption({
    tooltip: {
      trigger: 'axis',
      formatter(params: any) {
        let html = `<div style="font-weight:600;margin-bottom:4px">${params[0].axisValue}</div>`
        for (const p of params) {
          const unit = p.seriesName === '成功率' ? '%' : p.seriesName === '调用次数' ? '次' : 'ms'
          html += `<div>${p.marker} ${p.seriesName}: <b>${p.value}${unit}</b></div>`
        }
        return html
      }
    },
    legend: {
      data: ['平均耗时', '调用次数', '成功率'],
      top: 0
    },
    grid: { left: 60, right: 60, top: 40, bottom: 40 },
    xAxis: {
      type: 'category',
      data: categories,
      axisLabel: { interval: 0, rotate: entries.length > 5 ? 20 : 0 }
    },
    yAxis: [
      {
        type: 'value',
        name: '耗时 (ms) / 次数',
        position: 'left'
      },
      {
        type: 'value',
        name: '成功率 (%)',
        position: 'right',
        min: 0,
        max: 100,
        axisLabel: { formatter: '{value}%' }
      }
    ],
    series: [
      {
        name: '平均耗时',
        type: 'bar',
        data: avgData,
        itemStyle: { color: '#409EFF', borderRadius: [3, 3, 0, 0] },
        barMaxWidth: 30
      },
      {
        name: '调用次数',
        type: 'bar',
        data: countData,
        itemStyle: { color: '#909399', borderRadius: [3, 3, 0, 0] },
        barMaxWidth: 30
      },
      {
        name: '成功率',
        type: 'line',
        yAxisIndex: 1,
        data: successData,
        smooth: true,
        symbol: 'circle',
        symbolSize: 8,
        lineStyle: { width: 2, color: '#67C23A' },
        itemStyle: { color: '#67C23A' },
        areaStyle: { color: 'rgba(103,194,58,0.08)' }
      }
    ]
  }, true)
}

// Resize handler
function handleResize() {
  barChartInstance?.resize()
  successChartInstance?.resize()
}

// Format duration
function formatDuration(seconds: number): string {
  if (seconds < 0.001) return '< 1ms'
  if (seconds < 1) return `${(seconds * 1000).toFixed(1)}ms`
  return `${seconds.toFixed(2)}s`
}

// Format uptime
function formatUptime(seconds: number): string {
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = Math.floor(seconds % 60)
  if (hours > 0) return `${hours}h ${minutes}m ${secs}s`
  if (minutes > 0) return `${minutes}m ${secs}s`
  return `${secs}s`
}

// Format percentage
function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

// Clear performance data
async function handleClear() {
  try {
    await ElMessageBox.confirm(
      '确定要清空所有性能监控数据吗？此操作不可恢复。',
      '确认清空',
      { type: 'warning' }
    )
    await clearPerformanceData()
    ElMessage.success('已清空性能数据')
    loadPerformanceData()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.detail || '清空失败')
    }
  }
}

// Export report
async function handleExport() {
  try {
    const response = await exportPerformanceReport()
    const content = typeof response.data === 'string' ? response.data : String(response.data)
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `performance_report_${new Date().toISOString().split('T')[0]}.txt`
    link.click()
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '导出失败')
  }
}

// Format start time
function formatStartTime(isoString: string): string {
  return new Date(isoString).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })
}

// Lifecycle
onMounted(() => {
  loadPerformanceData()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  barChartInstance?.dispose()
  successChartInstance?.dispose()
})
</script>

<template>
  <div class="performance-container">
    <!-- Header -->
    <div class="page-header">
      <div class="header-left">
        <h1>性能监控</h1>
        <p class="page-description">API调用性能指标监控</p>
      </div>
      <div class="header-right">
        <el-button :icon="Refresh" @click="loadPerformanceData">刷新</el-button>
        <el-button :icon="Download" @click="handleExport">导出报告</el-button>
        <el-button type="danger" :icon="Delete" @click="handleClear">清空数据</el-button>
      </div>
    </div>

    <!-- Summary Cards -->
    <div v-loading="loading" class="summary-cards">
      <el-card class="summary-card" shadow="never">
        <div class="summary-icon">
          <el-icon size="24"><Timer /></el-icon>
        </div>
        <div class="summary-content">
          <div class="summary-value">{{ summary?.uptimeFormatted || '-' }}</div>
          <div class="summary-label">运行时长</div>
        </div>
      </el-card>
      <el-card class="summary-card" shadow="never">
        <div class="summary-icon">
          <el-icon size="24"><Odometer /></el-icon>
        </div>
        <div class="summary-content">
          <div class="summary-value">{{ summary?.totalRequests || 0 }}</div>
          <div class="summary-label">总请求数</div>
        </div>
      </el-card>
      <el-card class="summary-card" shadow="never">
        <div class="summary-icon success">
          <el-icon size="24"><Odometer /></el-icon>
        </div>
        <div class="summary-content">
          <div class="summary-value">{{ summary ? formatPercent(summary.overallSuccessRate) : '-' }}</div>
          <div class="summary-label">成功率</div>
        </div>
      </el-card>
      <el-card class="summary-card" shadow="never">
        <div class="summary-content">
          <div class="summary-value small">{{ summary ? formatStartTime(summary.startTime) : '-' }}</div>
          <div class="summary-label">启动时间</div>
        </div>
      </el-card>
    </div>

    <!-- Charts Row -->
    <div class="charts-row">
      <!-- Bar Chart: P50/P95/P99 -->
      <el-card class="chart-card" shadow="never">
        <template #header><span>响应时间分布 (P50 / P95 / P99)</span></template>
        <div v-if="hasData" ref="barChartRef" class="chart-box" />
        <div v-else class="empty-box">
          <el-empty description="暂无性能数据" :image-size="60" />
        </div>
      </el-card>
      <!-- Mixed Chart: avg + count + success rate -->
      <el-card class="chart-card" shadow="never">
        <template #header><span>调用概览 (平均耗时 / 次数 / 成功率)</span></template>
        <div v-if="hasData" ref="successChartRef" class="chart-box" />
        <div v-else class="empty-box">
          <el-empty description="暂无性能数据" :image-size="60" />
        </div>
      </el-card>
    </div>

    <!-- Metrics Table -->
    <el-card class="table-card" shadow="never">
      <template #header><span>详细指标</span></template>
      <el-table :data="Object.entries(metrics).map(([k, v]) => ({ key: k, ...v }))" stripe>
        <el-table-column label="指标" width="150">
          <template #default="{ row }">{{ getMetricLabel(row.key) }}</template>
        </el-table-column>
        <el-table-column prop="count" label="调用次数" width="100" align="right" />
        <el-table-column label="成功率" width="100" align="right">
          <template #default="{ row }">
            <el-tag :type="row.successRate >= 0.95 ? 'success' : row.successRate >= 0.8 ? 'warning' : 'danger'" size="small">
              {{ formatPercent(row.successRate) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="平均耗时" width="120" align="right">
          <template #default="{ row }">{{ formatDuration(row.avgDuration) }}</template>
        </el-table-column>
        <el-table-column label="P50" width="100" align="right">
          <template #default="{ row }">{{ formatDuration(row.p50Duration) }}</template>
        </el-table-column>
        <el-table-column label="P95" width="100" align="right">
          <template #default="{ row }"><span class="warning-text">{{ formatDuration(row.p95Duration) }}</span></template>
        </el-table-column>
        <el-table-column label="P99" width="100" align="right">
          <template #default="{ row }"><span class="danger-text">{{ formatDuration(row.p99Duration) }}</span></template>
        </el-table-column>
        <el-table-column label="最小/最大" min-width="150">
          <template #default="{ row }">{{ formatDuration(row.minDuration) }} / {{ formatDuration(row.maxDuration) }}</template>
        </el-table-column>
      </el-table>
      <el-empty v-if="Object.keys(metrics).length === 0" description="暂无性能数据" />
    </el-card>
  </div>
</template>

<style scoped>
.performance-container {
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
}

.header-left h1 {
  font-size: 24px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin: 0 0 8px 0;
}

.page-description {
  font-size: 14px;
  color: var(--el-text-color-secondary);
  margin: 0;
}

.header-right {
  display: flex;
  gap: 12px;
}

.summary-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.summary-card :deep(.el-card__body) {
  display: flex;
  align-items: center;
  gap: 16px;
  width: 100%;
}

.summary-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  background-color: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.summary-icon.success {
  background-color: var(--el-color-success-light-9);
  color: var(--el-color-success);
}

.summary-content { flex: 1; }

.summary-value {
  font-size: 24px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  line-height: 1.2;
}

.summary-value.small {
  font-size: 14px;
  font-weight: 500;
}

.summary-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}

.charts-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  margin-bottom: 20px;
}

.chart-card { position: relative; }

.chart-box {
  width: 100%;
  height: 360px;
}

.empty-box {
  width: 100%;
  height: 360px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.table-card { margin-bottom: 20px; }

.warning-text { color: var(--el-color-warning); }
.danger-text { color: var(--el-color-danger); }

@media (max-width: 960px) {
  .charts-row { grid-template-columns: 1fr; }
}

@media (max-width: 768px) {
  .page-header { flex-direction: column; gap: 16px; }
  .header-right { width: 100%; flex-wrap: wrap; }
  .summary-cards { grid-template-columns: repeat(2, 1fr); }
}
</style>
