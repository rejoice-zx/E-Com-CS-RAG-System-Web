<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Download, TrendCharts, PieChart, Delete } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import {
  getStatisticsOverview,
  getDailyStatistics,
  getCategoryDistribution,
  exportStatisticsReport,
  deleteStatisticsData,
  type StatisticsDeleteMode,
} from '@/api/statistics'
import type { StatisticsOverview, DailyStatistics, CategoryDistribution } from '@/types'

// Overview data
const overview = ref<StatisticsOverview | null>(null)
const overviewLoading = ref(false)

// Daily statistics
const dailyStats = ref<DailyStatistics[]>([])
const dailyLoading = ref(false)
const dateRange = ref<[Date, Date] | null>(null)

// Category distribution
const categoryData = ref<CategoryDistribution | null>(null)
const categoryLoading = ref(false)

// Chart DOM refs
const trendChartRef = ref<HTMLElement | null>(null)
const knowledgePieRef = ref<HTMLElement | null>(null)
const productPieRef = ref<HTMLElement | null>(null)

// ECharts instances
let trendChart: echarts.ECharts | null = null
let knowledgePie: echarts.ECharts | null = null
let productPie: echarts.ECharts | null = null

const deleteDialogVisible = ref(false)
const deleteMode = ref<StatisticsDeleteMode>('reset_all')
const deleteDateRange = ref<[Date, Date] | null>(null)
const deleteLoading = ref(false)

function formatLocalDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

// Load overview statistics
async function loadOverview() {
  overviewLoading.value = true
  try {
    const response = await getStatisticsOverview()
    overview.value = response.data
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '加载统计概览失败')
  } finally {
    overviewLoading.value = false
  }
}

// Load daily statistics
async function loadDailyStats() {
  dailyLoading.value = true
  try {
    const params: { start_date?: string; end_date?: string } = {}
    if (dateRange.value) {
      params.start_date = formatLocalDate(dateRange.value[0])
      params.end_date = formatLocalDate(dateRange.value[1])
    }
    const response = await getDailyStatistics(params)
    dailyStats.value = response.data
    await nextTick()
    renderTrendChart()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '加载每日统计失败')
  } finally {
    dailyLoading.value = false
  }
}

// Load category distribution
async function loadCategoryDistribution() {
  categoryLoading.value = true
  try {
    const response = await getCategoryDistribution()
    categoryData.value = response.data
    await nextTick()
    renderPieCharts()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '加载分类分布失败')
  } finally {
    categoryLoading.value = false
  }
}

// Render trend chart with ECharts
function renderTrendChart() {
  if (!trendChartRef.value || dailyStats.value.length === 0) return

  if (!trendChart) {
    trendChart = echarts.init(trendChartRef.value)
  }

  const dates = dailyStats.value.map(d => d.date)
  const conversations = dailyStats.value.map(d => d.conversations)
  const messages = dailyStats.value.map(d => d.messages)

  trendChart.setOption({
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' }
    },
    legend: {
      data: ['对话数', '消息数'],
      top: 0
    },
    grid: {
      left: '3%', right: '4%', bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: dates
    },
    yAxis: { type: 'value' },
    series: [
      {
        name: '对话数',
        type: 'line',
        smooth: true,
        itemStyle: { color: '#409EFF' },
        areaStyle: { color: 'rgba(64,158,255,0.15)' },
        data: conversations
      },
      {
        name: '消息数',
        type: 'line',
        smooth: true,
        itemStyle: { color: '#67C23A' },
        areaStyle: { color: 'rgba(103,194,58,0.15)' },
        data: messages
      }
    ]
  })
}

// Render pie charts with ECharts
function renderPieCharts() {
  if (!categoryData.value) return
  renderSinglePie(knowledgePieRef.value, categoryData.value.knowledge, '知识库分类分布', 'knowledgePie')
  renderSinglePie(productPieRef.value, categoryData.value.products, '商品分类分布', 'productPie')
}

function renderSinglePie(el: HTMLElement | null, data: Record<string, number>, title: string, which: string) {
  if (!el) return

  let chart: echarts.ECharts | null = which === 'knowledgePie' ? knowledgePie : productPie
  if (!chart) {
    chart = echarts.init(el)
    if (which === 'knowledgePie') knowledgePie = chart
    else productPie = chart
  }

  const seriesData = Object.entries(data).map(([name, value]) => ({ name, value }))

  chart.setOption({
    title: {
      text: title,
      left: 'center',
      textStyle: { fontSize: 14, fontWeight: 500 }
    },
    tooltip: {
      trigger: 'item',
      formatter: '{b}: {c} ({d}%)'
    },
    legend: {
      orient: 'horizontal',
      bottom: 0,
      type: 'scroll'
    },
    series: [
      {
        type: 'pie',
        radius: ['35%', '60%'],
        center: ['50%', '50%'],
        avoidLabelOverlap: true,
        itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
        label: { show: true, formatter: '{b}: {c}' },
        data: seriesData.length > 0 ? seriesData : [{ name: '暂无数据', value: 0 }]
      }
    ]
  })
}

// Export report
async function handleExport() {
  try {
    const response = await exportStatisticsReport()
    const content = typeof response.data === 'string' ? response.data : (response.data as any)?.content || ''
    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `statistics_report_${new Date().toISOString().split('T')[0]}.md`
    link.click()
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '导出失败')
  }
}

// Refresh all
function refreshAll() {
  loadOverview()
  loadDailyStats()
  loadCategoryDistribution()
}

function openDeleteDialog() {
  deleteMode.value = 'reset_all'
  deleteDateRange.value = null
  deleteDialogVisible.value = true
}

async function handleDeleteStatisticsData() {
  if (deleteMode.value === 'date_range' && !deleteDateRange.value) {
    ElMessage.warning('请选择要删除的时间范围')
    return
  }

  const secondConfirmText =
    deleteMode.value === 'reset_all'
      ? '你将清空当前统计数据，所有统计计数器将归零。此操作不可恢复，是否继续？'
      : '你将删除指定时间段统计数据。此操作不可恢复，是否继续？'
  try {
    await ElMessageBox.confirm(secondConfirmText, '二次确认', {
      type: 'warning',
      confirmButtonText: '确认删除',
      cancelButtonText: '取消'
    })
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.detail || '取消失败')
    }
    return
  }

  deleteLoading.value = true
  try {
    const payload: {
      mode: StatisticsDeleteMode
      start_date?: string
      end_date?: string
    } = { mode: deleteMode.value }
    if (deleteMode.value === 'date_range' && deleteDateRange.value) {
      payload.start_date = formatLocalDate(deleteDateRange.value[0])
      payload.end_date = formatLocalDate(deleteDateRange.value[1])
    }

    const response = await deleteStatisticsData(payload)
    ElMessage.success(
      response.data.message || '统计数据已删除'
    )
    deleteDialogVisible.value = false
    refreshAll()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '删除统计数据失败')
  } finally {
    deleteLoading.value = false
  }
}

// Resize handler
function handleResize() {
  trendChart?.resize()
  knowledgePie?.resize()
  productPie?.resize()
}

// Watch date range changes
watch(dateRange, () => {
  loadDailyStats()
})

// Initialize
onMounted(() => {
  refreshAll()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  trendChart?.dispose()
  knowledgePie?.dispose()
  productPie?.dispose()
})
</script>

<template>
  <div class="statistics-container">
    <!-- Header -->
    <div class="page-header">
      <div class="header-left">
        <h1>数据统计</h1>
        <p class="page-description">系统使用情况统计与分析</p>
      </div>
      <div class="header-right">
        <el-button :icon="Refresh" @click="refreshAll">刷新</el-button>
        <el-button type="primary" :icon="Download" @click="handleExport">导出报告</el-button>
        <el-button type="danger" :icon="Delete" @click="openDeleteDialog">删除数据</el-button>
      </div>
    </div>

    <!-- Overview Cards -->
    <div v-loading="overviewLoading" class="overview-cards">
      <el-card class="stat-card" shadow="never">
        <div class="stat-content">
          <div class="stat-value">{{ overview?.totalConversations || 0 }}</div>
          <div class="stat-label">总对话数</div>
        </div>
        <div class="stat-extra">今日: {{ overview?.conversationsToday || 0 }}</div>
      </el-card>
      <el-card class="stat-card" shadow="never">
        <div class="stat-content">
          <div class="stat-value">{{ overview?.totalMessages || 0 }}</div>
          <div class="stat-label">总消息数</div>
        </div>
      </el-card>
      <el-card class="stat-card" shadow="never">
        <div class="stat-content">
          <div class="stat-value">{{ overview?.totalKnowledgeItems || 0 }}</div>
          <div class="stat-label">知识库条目</div>
        </div>
      </el-card>
      <el-card class="stat-card" shadow="never">
        <div class="stat-content">
          <div class="stat-value">{{ overview?.totalProducts || 0 }}</div>
          <div class="stat-label">商品数量</div>
        </div>
      </el-card>
      <el-card class="stat-card" shadow="never">
        <div class="stat-content">
          <div class="stat-value">{{ overview?.totalUsers || 0 }}</div>
          <div class="stat-label">用户数量</div>
        </div>
      </el-card>
      <el-card class="stat-card" shadow="never">
        <div class="stat-content">
          <div class="stat-value">{{ overview?.avgResponseTime ? overview.avgResponseTime.toFixed(0) + 'ms' : '-' }}</div>
          <div class="stat-label">平均响应时间</div>
        </div>
      </el-card>
    </div>

    <!-- Trend Chart -->
    <el-card class="chart-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span><el-icon><TrendCharts /></el-icon> 对话趋势</span>
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            size="small"
            style="width: 260px"
          />
        </div>
      </template>
      <div v-loading="dailyLoading" class="chart-container">
        <div ref="trendChartRef" class="echarts-box" />
        <el-empty v-if="dailyStats.length === 0 && !dailyLoading" description="暂无数据" :image-size="80" />
      </div>
    </el-card>

    <!-- Category Distribution -->
    <div class="pie-charts">
      <el-card class="chart-card pie-card" shadow="never">
        <template #header>
          <span><el-icon><PieChart /></el-icon> 知识库分类分布</span>
        </template>
        <div v-loading="categoryLoading" class="chart-container">
          <div ref="knowledgePieRef" class="echarts-box" />
        </div>
      </el-card>
      <el-card class="chart-card pie-card" shadow="never">
        <template #header>
          <span><el-icon><PieChart /></el-icon> 商品分类分布</span>
        </template>
        <div v-loading="categoryLoading" class="chart-container">
          <div ref="productPieRef" class="echarts-box" />
        </div>
      </el-card>
    </div>

    <el-dialog
      v-model="deleteDialogVisible"
      title="删除统计数据"
      width="520px"
      destroy-on-close
    >
      <el-alert
        title="此操作不可恢复"
        type="warning"
        :closable="false"
        show-icon
      />
      <div class="delete-options-wrap">
        <el-radio-group v-model="deleteMode" class="delete-options">
          <el-radio label="reset_all" class="delete-option">清空当前数据</el-radio>
          <el-radio label="date_range" class="delete-option">删除指定时间段数据</el-radio>
        </el-radio-group>
      </div>

      <div v-if="deleteMode === 'date_range'" class="delete-range-wrap">
        <el-date-picker
          v-model="deleteDateRange"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          style="width: 100%"
        />
      </div>

      <template #footer>
        <el-button @click="deleteDialogVisible = false">取消</el-button>
        <el-button type="danger" :loading="deleteLoading" @click="handleDeleteStatisticsData">
          删除
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.statistics-container {
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

.overview-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  text-align: center;
}

.stat-content {
  padding: 8px 0;
}

.stat-value {
  font-size: 32px;
  font-weight: 600;
  color: var(--el-color-primary);
  line-height: 1.2;
}

.stat-label {
  font-size: 14px;
  color: var(--el-text-color-secondary);
  margin-top: 8px;
}

.stat-extra {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 8px;
  margin-top: 8px;
}

.chart-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-header span {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
}

.chart-container {
  min-height: 300px;
  position: relative;
}

.echarts-box {
  width: 100%;
  height: 300px;
}

.pie-charts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
  gap: 20px;
}

.pie-card .echarts-box {
  height: 320px;
}

.delete-options-wrap {
  margin-top: 16px;
}

.delete-options {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 24px;
}

.delete-option {
  margin-right: 0;
}

.delete-range-wrap {
  margin-top: 16px;
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    gap: 16px;
  }

  .header-right {
    width: 100%;
    justify-content: flex-end;
  }

  .overview-cards {
    grid-template-columns: repeat(2, 1fr);
  }

  .pie-charts {
    grid-template-columns: 1fr;
  }
}
</style>
