<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Refresh, Download, Delete, ArrowDown } from '@element-plus/icons-vue'
import { getLogs, downloadLogs, clearLogs } from '@/api/logs'
import type { LogEntry } from '@/types'

// State
const loading = ref(false)
const logList = ref<LogEntry[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(50)

// Filters
const filters = reactive({
  level: '',
  keyword: '',
  startTime: '',
  endTime: ''
})

// Date range
const dateRange = ref<[Date, Date] | null>(null)

// Log levels
const logLevels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']

// Load logs
async function loadLogs() {
  loading.value = true
  try {
    const params: any = {
      page: currentPage.value,
      page_size: pageSize.value
    }
    
    if (filters.level) params.level = filters.level
    if (filters.keyword) params.keyword = filters.keyword
    if (dateRange.value) {
      params.start_time = dateRange.value[0].toISOString()
      params.end_time = dateRange.value[1].toISOString()
    }
    
    const response = await getLogs(params)
    const data = response.data
    logList.value = data.items || []
    total.value = data.total || 0
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '加载日志失败')
  } finally {
    loading.value = false
  }
}

// Handle search
function handleSearch() {
  currentPage.value = 1
  loadLogs()
}

// Handle reset
function handleReset() {
  filters.level = ''
  filters.keyword = ''
  dateRange.value = null
  currentPage.value = 1
  loadLogs()
}

// Handle page change
function handlePageChange(page: number) {
  currentPage.value = page
  loadLogs()
}

// Handle page size change
function handleSizeChange(size: number) {
  pageSize.value = size
  currentPage.value = 1
  loadLogs()
}

// Download logs
async function handleDownload(logType: 'app' | 'error') {
  try {
    const response = await downloadLogs(logType)
    const blob = response.data as Blob
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${logType}_${new Date().toISOString().split('T')[0]}.log`
    link.click()
    URL.revokeObjectURL(url)
    ElMessage.success('下载成功')
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '下载失败')
  }
}

// Clear logs
async function handleClear(logType: 'app' | 'error') {
  try {
    await ElMessageBox.confirm(
      `确定要清空${logType === 'app' ? '应用' : '错误'}日志吗？此操作不可恢复。`,
      '确认清空',
      { type: 'warning' }
    )
    await clearLogs(logType)
    ElMessage.success('已清空日志')
    loadLogs()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.detail || '清空失败')
    }
  }
}

// Get level tag type
function getLevelType(level: string): string {
  const typeMap: Record<string, string> = {
    'DEBUG': 'info',
    'INFO': '',
    'WARNING': 'warning',
    'ERROR': 'danger',
    'CRITICAL': 'danger'
  }
  return typeMap[level] || 'info'
}

// Format timestamp
function formatTimestamp(timestamp: string): string {
  return new Date(timestamp).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })
}

// Initialize
onMounted(() => {
  loadLogs()
})
</script>

<template>
  <div class="logs-container">
    <!-- Header -->
    <div class="page-header">
      <div class="header-left">
        <h1>日志管理</h1>
        <p class="page-description">
          查看和管理系统日志
        </p>
      </div>
      <div class="header-right">
        <el-dropdown @command="handleDownload">
          <el-button :icon="Download">
            下载日志<el-icon class="el-icon--right">
              <arrow-down />
            </el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="app">
                应用日志
              </el-dropdown-item>
              <el-dropdown-item command="error">
                错误日志
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-dropdown @command="handleClear">
          <el-button
            type="danger"
            :icon="Delete"
          >
            清空日志<el-icon class="el-icon--right">
              <arrow-down />
            </el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="app">
                清空应用日志
              </el-dropdown-item>
              <el-dropdown-item command="error">
                清空错误日志
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <!-- Toolbar -->
    <el-card
      class="toolbar-card"
      shadow="never"
    >
      <div class="toolbar">
        <div class="toolbar-left">
          <el-select
            v-model="filters.level"
            placeholder="日志级别"
            clearable
            style="width: 140px"
          >
            <el-option
              v-for="level in logLevels"
              :key="level"
              :label="level"
              :value="level"
            />
          </el-select>
          <el-input
            v-model="filters.keyword"
            placeholder="搜索关键词"
            clearable
            style="width: 200px"
            @keyup.enter="handleSearch"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
          <el-date-picker
            v-model="dateRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            style="width: 360px"
          />
          <el-button
            type="primary"
            :icon="Search"
            @click="handleSearch"
          >
            搜索
          </el-button>
          <el-button
            :icon="Refresh"
            @click="handleReset"
          >
            重置
          </el-button>
        </div>
      </div>
    </el-card>

    <!-- Log Table -->
    <el-card
      class="table-card"
      shadow="never"
    >
      <el-table
        v-loading="loading"
        :data="logList"
        stripe
      >
        <el-table-column
          label="时间"
          width="180"
        >
          <template #default="{ row }">
            {{ formatTimestamp(row.timestamp) }}
          </template>
        </el-table-column>
        <el-table-column
          label="级别"
          width="100"
        >
          <template #default="{ row }">
            <el-tag
              :type="getLevelType(row.level)"
              size="small"
            >
              {{ row.level }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="source"
          label="来源"
          width="150"
          show-overflow-tooltip
        />
        <el-table-column
          prop="message"
          label="消息"
          min-width="400"
        >
          <template #default="{ row }">
            <div class="log-message">
              {{ row.message }}
            </div>
          </template>
        </el-table-column>
      </el-table>
      
      <!-- Pagination -->
      <div class="pagination">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[20, 50, 100, 200]"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          @current-change="handlePageChange"
          @size-change="handleSizeChange"
        />
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.logs-container {
  padding: 20px;
  max-width: 1600px;
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

.toolbar-card,
.table-card {
  margin-bottom: 20px;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.log-message {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  white-space: pre-wrap;
  word-break: break-all;
  line-height: 1.5;
}

/* Responsive */
@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    gap: 16px;
  }
  
  .header-right {
    width: 100%;
    flex-wrap: wrap;
  }
  
  .toolbar-left {
    width: 100%;
  }
}
</style>
