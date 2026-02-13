<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { 
  ChatDotRound, User, Check, Position, 
  Refresh, Edit, ArrowRight, Warning, Document, Delete, Search 
} from '@element-plus/icons-vue'
import { getConversations, getMessages, transferToHuman, deleteConversation, updateConversation, countMessagesByDateRange, batchDeleteMessagesByDate } from '@/api/chat'
import { getKnowledge, updateKnowledge, getKnowledgeCategories } from '@/api/knowledge'
import { getSettings } from '@/api/settings'
import type { Message, RAGTrace } from '@/types'

// Types
interface SessionData {
  id: string
  title: string
  status: string
  customer_id?: string
  customer_name?: string
  timestamp: string
  confidence: number
  messageCount: number
  messages: Message[]
}

// State
const loading = ref(false)
const sessions = ref<SessionData[]>([])
const currentSession = ref<SessionData | null>(null)
const currentMessages = ref<Message[]>([])
const selectedMessageIndex = ref(0)

// Filter
const statusFilter = ref('全部')
const statusOptions = ['全部', '进行中', '待处理', '低置信度', '转人工', '已解决']

// RAG Config
const ragConfig = reactive({
  topK: 5,
  similarityThreshold: 0.5
})

// Collapsible sections
const finalPromptExpanded = ref(false)
const knowledgeEditVisible = ref(false)
const knowledgeSaving = ref(false)
const knowledgeLoading = ref(false)
const editingKnowledgeId = ref('')
const selectedKnowledgeCandidateId = ref('')
const knowledgeEditForm = reactive({
  question: '',
  answer: '',
  keywords: [] as string[],
  category: ''
})
const knowledgeKwInput = ref('')
const knowledgeCategories = ref<string[]>([])

async function loadKnowledgeCategories() {
  try {
    const res = await getKnowledgeCategories()
    knowledgeCategories.value = (res.data.categories || []).filter((c: string) => c !== '全部')
  } catch { /* keep current */ }
}

function pushKnowledgeKw() {
  const v = knowledgeKwInput.value.trim()
  if (v && !knowledgeEditForm.keywords.includes(v)) {
    knowledgeEditForm.keywords.push(v)
  }
  knowledgeKwInput.value = ''
}

// Computed: filtered sessions
const filteredSessions = computed(() => {
  let list = sessions.value
  if (statusFilter.value !== '全部') {
    list = list.filter(s => s.status === statusFilter.value)
  }
  // 按时间检索：只保留在时间段内有消息的会话
  if (searchActive.value && searchRange.value) {
    const [start, end] = searchRange.value
    const startDate = formatDateLocal(start)
    const endDate = formatDateLocal(end)
    list = list.filter(s =>
      s.messages.some(msg => {
        const msgDate = formatDateLocal(new Date(msg.timestamp))
        return msgDate >= startDate && msgDate <= endDate
      })
    )
  }
  return list
})

// Computed: 用户会话（customer_id 以 user_ 开头）
const userSessions = computed(() => {
  return filteredSessions.value.filter(s => s.customer_id && s.customer_id.startsWith('user_'))
})

// Computed: 访客会话（customer_id 以 visitor_ 开头或其他）
const visitorSessions = computed(() => {
  return filteredSessions.value.filter(s => !s.customer_id || !s.customer_id.startsWith('user_'))
})

// Computed: user messages for RAG trace selector
const userMessages = computed(() => {
  if (!currentMessages.value.length) return []
  return currentMessages.value
    .map((msg, index) => ({ msg, index }))
    .filter(({ msg }) => msg.role === 'user')
})

// Computed: current RAG trace
const currentRagTrace = computed((): RAGTrace | null => {
  if (!userMessages.value.length) return null
  const userMsg = userMessages.value[selectedMessageIndex.value]
  if (!userMsg) return null
  
  // Find the assistant message following this user message
  const nextIndex = userMsg.index + 1
  if (nextIndex < currentMessages.value.length) {
    const assistantMsg = currentMessages.value[nextIndex]
    console.log('Assistant message:', assistantMsg)
    console.log('rag_trace:', assistantMsg.rag_trace)
    if (assistantMsg.role === 'assistant' && assistantMsg.rag_trace) {
      return assistantMsg.rag_trace
    }
  }
  return null
})

const retrievedKnowledgeCandidates = computed(() => {
  const items = currentRagTrace.value?.retrieved_items || []
  return items
    .filter((item) => item && item.id)
    .slice(0, 5)
    .map((item) => ({
      id: String(item.id),
      question: item.question || '',
      score: Number(item.score || 0)
    }))
})

const hasRetrievedKnowledge = computed(() => retrievedKnowledgeCandidates.value.length > 0)

// Computed: Query Rewrite 差异分析
const rewriteDiff = computed(() => {
  const result = { removed: [] as string[], added: [] as string[] }
  const trace = currentRagTrace.value
  if (!trace || !trace.rewritten_query || trace.rewritten_query === trace.query) return result
  
  const origTokens = trace.query.split(/\s+/).filter(Boolean)
  const rewriteTokens = trace.rewritten_query.split(/\s+/).filter(Boolean)
  
  const origSet = new Set(origTokens)
  const rewriteSet = new Set(rewriteTokens)
  
  // 被移除的词（在原始中有，改写中没有）
  for (const t of origTokens) {
    if (!rewriteSet.has(t)) result.removed.push(t)
  }
  // 被添加的词（在改写中有，原始中没有）
  for (const t of rewriteTokens) {
    if (!origSet.has(t)) result.added.push(t)
  }
  
  return result
})

// Load sessions
async function loadSessions() {
  loading.value = true
  try {
    const response = await getConversations({ page: 1, page_size: 100 })
    const convs = response.data.items
    
    // Transform to session data
    sessions.value = await Promise.all(convs.map(async (conv) => {
      // Load messages for each conversation
      const msgResponse = await getMessages(conv.id, { page: 1, page_size: 100, include_deleted: true })
      const messages = msgResponse.data.items
      
      // Calculate average confidence
      const confidences = messages
        .filter(m => m.role === 'assistant' && m.confidence != null)
        .map(m => m.confidence!)
      const avgConfidence: number = confidences.length > 0 
        ? confidences.reduce((a, b) => a + b, 0) / confidences.length 
        : 0.5
      
      // Determine status
      let status = '进行中'
      if (conv.status === 'pending_human') status = '转人工'
      else if (conv.status === 'human_handling') status = '转人工'
      else if (conv.status === 'human_closed') status = '已解决'
      else if (avgConfidence < 0.4) status = '低置信度'
      
      return {
        id: conv.id,
        title: conv.title,
        status,
        customer_id: conv.customer_id,
        customer_name: (conv as any).customer_name,
        timestamp: conv.updated_at || conv.updatedAt,
        confidence: avgConfidence,
        messageCount: Math.floor(messages.length / 2),
        messages
      }
    }))
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '加载会话列表失败')
  } finally {
    loading.value = false
  }
}

// Load RAG config
async function loadRagConfig() {
  try {
    const response = await getSettings()
    if (response.data?.rag) {
      ragConfig.topK = response.data.rag.top_k ?? ragConfig.topK
      ragConfig.similarityThreshold = response.data.rag.similarity_threshold ?? ragConfig.similarityThreshold
    }
  } catch (error) {
    console.error('Failed to load RAG config:', error)
  }
}

// Select session
function selectSession(session: SessionData) {
  currentSession.value = session
  currentMessages.value = session.messages
  selectedMessageIndex.value = 0
}

// Computed: 展示的消息（受检索时间段过滤）
const displayMessages = computed(() => {
  if (!searchActive.value || !searchRange.value) return currentMessages.value
  const [start, end] = searchRange.value
  // el-date-picker 返回的是本地时间 Date 对象
  // msg.timestamp 是 UTC ISO 字符串（带 Z），new Date() 会正确解析
  // 比较时统一转为本地日期字符串（YYYY-MM-DD）进行日期级别比较
  const startDate = formatDateLocal(start)
  const endDate = formatDateLocal(end)
  return currentMessages.value.filter(msg => {
    const msgDate = formatDateLocal(new Date(msg.timestamp))
    return msgDate >= startDate && msgDate <= endDate
  })
})

// 将 Date 对象格式化为 Asia/Shanghai 时区的 YYYY-MM-DD 字符串
function formatDateLocal(d: Date): string {
  const parts = d.toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
  return parts // sv-SE locale gives YYYY-MM-DD format
}

// Mark as resolved
async function markResolved() {
  if (!currentSession.value) return
  
  try {
    await updateConversation(currentSession.value.id, { status: 'human_closed' })
    currentSession.value.status = '已解决'
    const idx = sessions.value.findIndex(s => s.id === currentSession.value!.id)
    if (idx >= 0) {
      sessions.value[idx].status = '已解决'
    }
    ElMessage.success('已标记为解决')
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '操作失败')
  }
}

// Transfer to human
async function handleTransferToHuman() {
  if (!currentSession.value) return
  
  try {
    await transferToHuman(currentSession.value.id)
    currentSession.value.status = '转人工'
    const idx = sessions.value.findIndex(s => s.id === currentSession.value!.id)
    if (idx >= 0) {
      sessions.value[idx].status = '转人工'
    }
    ElMessage.success('已转接人工客服')
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '转接失败')
  }
}

// Delete session
async function deleteSession(session: SessionData) {
  try {
    await ElMessageBox.confirm('确定要删除这个会话记录吗？', '确认删除', { type: 'warning' })
    await deleteConversation(session.id)
    sessions.value = sessions.value.filter(s => s.id !== session.id)
    if (currentSession.value?.id === session.id) {
      currentSession.value = null
      currentMessages.value = []
    }
    ElMessage.success('会话记录已删除')
  } catch (error: any) {
    if (error !== 'cancel' && error?.toString() !== 'cancel') {
      ElMessage.error(error.response?.data?.detail || '删除失败')
    }
  }
}

function resetKnowledgeEditForm() {
  editingKnowledgeId.value = ''
  selectedKnowledgeCandidateId.value = ''
  knowledgeLoading.value = false
  knowledgeEditForm.question = ''
  knowledgeEditForm.answer = ''
  knowledgeEditForm.keywords = []
  knowledgeEditForm.category = ''
  knowledgeKwInput.value = ''
}

async function editKnowledge() {
  if (!hasRetrievedKnowledge.value) {
    ElMessage.warning('暂无相关知识')
    return
  }

  loadKnowledgeCategories()
  selectedKnowledgeCandidateId.value = retrievedKnowledgeCandidates.value[0].id
  knowledgeEditVisible.value = true
  await loadKnowledgeForEdit(selectedKnowledgeCandidateId.value)
}

async function loadKnowledgeForEdit(knowledgeId: string) {
  if (!knowledgeId) {
    return
  }

  knowledgeLoading.value = true
  try {
    const response = await getKnowledge(knowledgeId)
    const data = response.data
    editingKnowledgeId.value = String(data.id || '')
    knowledgeEditForm.question = data.question || ''
    knowledgeEditForm.answer = data.answer || ''
    knowledgeEditForm.keywords = Array.isArray(data.keywords) ? [...data.keywords] : []
    knowledgeEditForm.category = data.category || ''
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '加载知识条目失败')
  } finally {
    knowledgeLoading.value = false
  }
}

async function onKnowledgeCandidateChange(knowledgeId: string) {
  await loadKnowledgeForEdit(knowledgeId)
}

async function saveKnowledgeEdit() {
  if (!editingKnowledgeId.value) return
  if (!knowledgeEditForm.question.trim() || !knowledgeEditForm.answer.trim()) {
    ElMessage.warning('问题和答案不能为空')
    return
  }

  knowledgeSaving.value = true
  try {
    await updateKnowledge(editingKnowledgeId.value, {
      question: knowledgeEditForm.question.trim(),
      answer: knowledgeEditForm.answer.trim(),
      keywords: knowledgeEditForm.keywords,
      category: knowledgeEditForm.category.trim() || undefined
    })
    knowledgeEditVisible.value = false
    ElMessage.success('知识条目已更新')
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '保存知识条目失败')
  } finally {
    knowledgeSaving.value = false
  }
}

// Format time — 后端返回 UTC（带 Z 后缀），统一转为本地时间显示
function formatTime(timestamp: string): string {
  const d = new Date(timestamp)
  return d.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })
}

// Get status color (with slight transparency)
function getStatusColor(status: string): string {
  const colors: Record<string, string> = {
    '进行中': 'rgba(82, 196, 26, 0.85)',
    '待处理': 'rgba(250, 173, 20, 0.85)',
    '低置信度': 'rgba(255, 77, 79, 0.85)',
    '转人工': 'rgba(114, 46, 209, 0.85)',
    '已解决': 'rgba(24, 144, 255, 0.85)'
  }
  return colors[status] || 'rgba(153, 153, 153, 0.85)'
}

// Get score class for styling
function getScoreClass(score: number): string {
  if (score >= 0.7) return 'high'
  if (score >= 0.4) return 'medium'
  return 'low'
}

// Get confidence class
function getConfidenceClass(confidence: number): string {
  if (confidence >= 0.7) return 'high'
  if (confidence >= 0.4) return 'medium'
  return 'low'
}

// Get confidence level text
function getConfidenceLevel(confidence: number): string {
  if (confidence >= 0.7) return '高置信度'
  if (confidence >= 0.4) return '中置信度'
  return '低置信度'
}

// Get confidence action
function getConfidenceAction(confidence: number): string {
  if (confidence >= 0.7) return '正常回复'
  if (confidence >= 0.4) return '建议补充信息'
  return '建议转人工'
}

// Format customer_id for display
function formatCustomerId(session: SessionData): string {
  const cid = session.customer_id
  if (!cid || cid === 'anonymous') return '匿名用户'
  if (cid.startsWith('user_')) return session.customer_name || `用户 #${cid.slice(5)}`
  if (cid.startsWith('visitor_')) return `访客 ${cid.slice(8, 14)}`
  return cid
}

// --- 轮询逻辑 ---
let sessionRefreshTimer: ReturnType<typeof setInterval> | null = null

// Initialize
onMounted(() => {
  loadSessions()
  loadRagConfig()
  // 15秒自动刷新会话列表
  sessionRefreshTimer = setInterval(() => {
    // 静默刷新，不影响当前选中的会话
    loadSessionsSilent()
  }, 15000)
})

onUnmounted(() => {
  if (sessionRefreshTimer) {
    clearInterval(sessionRefreshTimer)
    sessionRefreshTimer = null
  }
})

// 静默刷新会话列表（不清除当前选中状态）
async function loadSessionsSilent() {
  try {
    const response = await getConversations({ page: 1, page_size: 100 })
    const convs = response.data.items
    
    // 只更新元数据，不重新拉取每个对话的消息（避免 N+1 请求）
    const updatedSessions: SessionData[] = []
    for (const conv of convs) {
      const existing = sessions.value.find(s => s.id === conv.id)
      
      if (existing) {
        // 已有的会话：只更新元数据
        let status = existing.status
        if (conv.status === 'pending_human' || conv.status === 'human_handling') status = '转人工'
        else if (conv.status === 'human_closed') status = '已解决'
        
        updatedSessions.push({
          ...existing,
          title: conv.title,
          customer_id: conv.customer_id,
          customer_name: (conv as any).customer_name,
          status,
          timestamp: conv.updated_at || conv.updatedAt,
        })
      } else {
        // 新出现的会话：拉取消息
        const msgResponse = await getMessages(conv.id, { page: 1, page_size: 100, include_deleted: true })
        const msgs = msgResponse.data.items
        
        const confidences = msgs
          .filter(m => m.role === 'assistant' && m.confidence != null)
          .map(m => m.confidence!)
        const avgConfidence: number = confidences.length > 0 
          ? confidences.reduce((a, b) => a + b, 0) / confidences.length 
          : 0.5
        
        let status = '进行中'
        if (conv.status === 'pending_human') status = '转人工'
        else if (conv.status === 'human_handling') status = '转人工'
        else if (conv.status === 'human_closed') status = '已解决'
        else if (avgConfidence < 0.4) status = '低置信度'
        
        updatedSessions.push({
          id: conv.id,
          title: conv.title,
          status,
          customer_id: conv.customer_id,
          customer_name: (conv as any).customer_name,
          timestamp: conv.updated_at || conv.updatedAt,
          confidence: avgConfidence,
          messageCount: Math.floor(msgs.length / 2),
          messages: msgs
        })
      }
    }
    
    sessions.value = updatedSessions
    
    // 如果当前选中的会话存在，刷新其消息
    if (currentSession.value) {
      const updated = updatedSessions.find(s => s.id === currentSession.value!.id)
      if (updated) {
        // 增量拉取当前选中会话的最新消息
        try {
          const lastId = updated.messages.length > 0
            ? Math.max(...updated.messages.map(m => m.id))
            : undefined
          const params: any = lastId
            ? { since_id: lastId, include_deleted: true }
            : { page: 1, page_size: 100, include_deleted: true }
          const msgResponse = await getMessages(currentSession.value.id, params)
          const newMsgs = msgResponse.data.items
          if (newMsgs.length > 0) {
            if (lastId) {
              // 增量追加，去重
              for (const msg of newMsgs) {
                if (!updated.messages.some(m => m.id === msg.id)) {
                  updated.messages.push(msg)
                }
              }
              updated.messageCount = Math.floor(updated.messages.length / 2)
              currentSession.value = updated
              currentMessages.value = updated.messages
            } else {
              updated.messages = newMsgs
              updated.messageCount = Math.floor(newMsgs.length / 2)
              currentSession.value = updated
              currentMessages.value = newMsgs
            }
          }
        } catch { /* ignore */ }
      }
    }
  } catch { /* ignore */ }
}

// ==================== 批量删除消息 ====================
const batchDeleteDialogVisible = ref(false)
const batchDeleteRange = ref<[Date, Date] | null>(null)
const batchDeleteLoading = ref(false)

// ==================== 按时间检索消息 ====================
const searchDialogVisible = ref(false)
const searchRange = ref<[Date, Date] | null>(null)
const searchActive = ref(false)

function openSearchDialog() {
  searchDialogVisible.value = true
}

function executeSearch() {
  if (!searchRange.value || searchRange.value.length < 2) {
    ElMessage.warning('请选择时间范围')
    return
  }
  searchActive.value = true
  searchDialogVisible.value = false
  ElMessage.success('已按时间段筛选消息')
}

function resetSearch() {
  const wasSearching = searchActive.value
  searchActive.value = false
  searchRange.value = null
  if (wasSearching) {
    // 重新选中当前会话以恢复完整消息列表
    if (currentSession.value) {
      currentMessages.value = currentSession.value.messages
    }
    ElMessage.success('已清空检索条件')
  }
  loadSessions()
}

async function handleBatchDelete(mode: string) {
  const now = new Date()
  let before: Date | null = null
  if (mode === '7days') {
    before = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
  } else if (mode === '30days') {
    before = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000)
  } else if (mode === 'custom') {
    batchDeleteDialogVisible.value = true
    return
  }

  if (!before) return
  await confirmAndDelete(before.toISOString(), undefined)
}

async function confirmCustomDelete() {
  if (!batchDeleteRange.value || batchDeleteRange.value.length < 2) {
    ElMessage.warning('请选择日期范围')
    return
  }
  const [start, end] = batchDeleteRange.value
  // after = start of range, before = end of range (end of day)
  const afterStr = new Date(start).toISOString()
  const endDate = new Date(end)
  endDate.setHours(23, 59, 59, 999)
  const beforeStr = endDate.toISOString()
  batchDeleteDialogVisible.value = false
  await confirmAndDelete(beforeStr, afterStr)
}

async function confirmAndDelete(before?: string, after?: string) {
  batchDeleteLoading.value = true
  try {
    const params: { before?: string; after?: string } = {}
    if (before) params.before = before
    if (after) params.after = after

    const countRes = await countMessagesByDateRange(params)
    const count = countRes.data.count

    if (count === 0) {
      ElMessage.info('该时间范围内没有消息')
      return
    }

    await ElMessageBox.confirm(
      `确定要删除 ${count} 条消息吗？此操作不可恢复。`,
      '确认批量删除',
      { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' }
    )

    const res = await batchDeleteMessagesByDate(params)
    ElMessage.success(res.data.message)
    await loadSessions()
  } catch (error: any) {
    if (error !== 'cancel' && error?.toString() !== 'cancel') {
      ElMessage.error(error.response?.data?.detail || '批量删除失败')
    }
  } finally {
    batchDeleteLoading.value = false
  }
}
</script>

<template>
  <div class="workbench-container">
    <!-- Left Panel: Session List -->
    <aside class="session-panel">
      <div class="panel-header">
        <h3>会话列表</h3>
        <div class="panel-header-actions">
          <el-button text :icon="Search" size="small" @click="openSearchDialog" title="按时间检索消息" />
          <el-dropdown trigger="click" @command="handleBatchDelete" :disabled="batchDeleteLoading">
            <el-button text :icon="Delete" size="small" :loading="batchDeleteLoading" title="批量删除消息" />
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="7days">删除七天前的所有消息</el-dropdown-item>
                <el-dropdown-item command="30days">删除三十天前的所有消息</el-dropdown-item>
                <el-dropdown-item command="custom" divided>自定义时间段</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-button text :icon="Refresh" size="small" @click="resetSearch" :title="searchActive ? '清空检索，刷新列表' : '刷新列表'" />
        </div>
      </div>
      
      <el-select v-model="statusFilter" placeholder="筛选状态" class="status-filter">
        <el-option v-for="opt in statusOptions" :key="opt" :label="opt" :value="opt" />
      </el-select>
      
      <div class="session-list-wrapper" v-loading="loading">
        <div v-if="searchActive" class="search-hint">
          🔍 检索结果：{{ filteredSessions.length }} 个会话
          <span v-if="currentSession">，当前会话 {{ displayMessages.length }} 条消息</span>
        </div>
        <!-- 用户会话 -->
        <div class="session-section">
          <div class="group-label">👤 用户会话 ({{ userSessions.length }})</div>
          <div class="session-scroll">
            <div
              v-for="session in userSessions"
              :key="session.id"
              class="session-item"
              :class="{ active: currentSession?.id === session.id }"
              @click="selectSession(session)"
            >
              <div class="session-header">
                <span class="status-badge" :style="{ backgroundColor: getStatusColor(session.status) }">{{ session.status }}</span>
                <span class="msg-count">💬 {{ session.messageCount }}轮对话</span>
                <span v-if="session.status === '已解决'" class="delete-btn" @click.stop="deleteSession(session)">🗑️</span>
                <span class="timestamp">{{ formatTime(session.timestamp) }}</span>
              </div>
              <div class="session-title">📋 {{ session.title }}</div>
              <div class="session-meta-row">
                <span class="session-confidence">平均置信度: {{ (session.confidence * 100).toFixed(0) }}%</span>
                <span class="customer-tag" v-if="session.customer_id">{{ formatCustomerId(session) }}</span>
              </div>
            </div>
            <el-empty v-if="userSessions.length === 0" description="暂无用户会话" :image-size="40" />
          </div>
        </div>

        <!-- 访客会话 -->
        <div class="session-section">
          <div class="group-label">🌐 访客会话 ({{ visitorSessions.length }})</div>
          <div class="session-scroll">
            <div
              v-for="session in visitorSessions"
              :key="session.id"
              class="session-item"
              :class="{ active: currentSession?.id === session.id }"
              @click="selectSession(session)"
            >
              <div class="session-header">
                <span class="status-badge" :style="{ backgroundColor: getStatusColor(session.status) }">{{ session.status }}</span>
                <span class="msg-count">💬 {{ session.messageCount }}轮对话</span>
                <span v-if="session.status === '已解决'" class="delete-btn" @click.stop="deleteSession(session)">🗑️</span>
                <span class="timestamp">{{ formatTime(session.timestamp) }}</span>
              </div>
              <div class="session-title">📋 {{ session.title }}</div>
              <div class="session-meta-row">
                <span class="session-confidence">平均置信度: {{ (session.confidence * 100).toFixed(0) }}%</span>
                <span class="customer-tag" v-if="session.customer_id">{{ formatCustomerId(session) }}</span>
              </div>
            </div>
            <el-empty v-if="visitorSessions.length === 0" description="暂无访客会话" :image-size="40" />
          </div>
        </div>
      </div>
    </aside>

    <!-- Center Panel: Conversation Detail -->
    <main class="conversation-panel">
      <template v-if="currentSession">
        <div class="panel-header">
          <h3>💬 {{ currentSession.title }}</h3>
        </div>
        
        <div class="message-list">
          <div v-if="searchActive" class="search-hint">
            🔍 时间段筛选中，共 {{ displayMessages.length }} 条消息匹配
          </div>
          <div
            v-for="msg in displayMessages"
            :key="msg.id"
            class="message-item"
            :class="msg.role"
          >
            <div class="message-avatar">
              <el-icon v-if="msg.role === 'user'"><User /></el-icon>
              <el-icon v-else-if="msg.role === 'human'"><Position /></el-icon>
              <el-icon v-else><ChatDotRound /></el-icon>
            </div>
            <div class="message-body">
              <div class="message-header">
                <span class="role-name">
                  {{ msg.role === 'user' ? '用户' : msg.role === 'human' ? (msg.human_agent_name ? `客服 · ${msg.human_agent_name}` : '客服') : 'AI客服' }}
                </span>
              </div>
              <div class="message-content">{{ msg.content }}</div>
            </div>
          </div>
        </div>
        
        <div class="action-bar">
          <el-button type="primary" :icon="Check" @click="markResolved">标记解决</el-button>
          <el-button :icon="Position" @click="handleTransferToHuman">转人工</el-button>
        </div>
      </template>
      
      <el-empty v-else description="选择一个会话查看详情" :image-size="100" />
    </main>

    <!-- Right Panel: RAG Trace -->
    <aside class="rag-panel">
      <div class="panel-header">
        <h3>RAG 追溯</h3>
      </div>
      
      <template v-if="currentSession && userMessages.length > 0">
        <!-- Message Selector -->
        <el-select 
          v-model="selectedMessageIndex" 
          placeholder="选择要追溯的问题"
          class="msg-selector"
        >
          <el-option
            v-for="(item, idx) in userMessages"
            :key="idx"
            :label="`Q${idx + 1}: ${item.msg.content.substring(0, 25)}${item.msg.content.length > 25 ? '...' : ''}`"
            :value="idx"
          />
        </el-select>
        
        <div class="trace-content">
          <template v-if="currentRagTrace">
            <!-- Query Rewrite -->
            <div class="trace-card">
              <div class="card-header">
                <span class="step-badge">1</span>
                <span class="card-title">Query Rewrite</span>
                <el-tag 
                  v-if="currentRagTrace.rewritten_query && currentRagTrace.rewritten_query !== currentRagTrace.query" 
                  type="success" size="small" effect="plain" round
                >已改写</el-tag>
                <el-tag v-else type="info" size="small" effect="plain" round>未改写</el-tag>
              </div>
              <div class="card-body">
                <div class="query-row">
                  <span class="query-label">原始查询</span>
                  <span class="query-text">{{ currentRagTrace.query }}</span>
                </div>
                <div class="query-row">
                  <span class="query-label">改写查询</span>
                  <span 
                    class="query-text" 
                    :class="{ 'query-changed': currentRagTrace.rewritten_query && currentRagTrace.rewritten_query !== currentRagTrace.query }"
                  >
                    {{ currentRagTrace.rewritten_query || currentRagTrace.query }}
                  </span>
                </div>
                <div class="query-row" v-if="rewriteDiff.removed.length || rewriteDiff.added.length">
                  <span class="query-label">改写详情</span>
                  <div class="rewrite-diff">
                    <span v-for="(word, i) in rewriteDiff.removed" :key="'r'+i" class="diff-removed">- {{ word }}</span>
                    <span v-for="(word, i) in rewriteDiff.added" :key="'a'+i" class="diff-added">+ {{ word }}</span>
                  </div>
                </div>
              </div>
            </div>
            
            <!-- Retriever -->
            <div class="trace-card">
              <div class="card-header">
                <span class="step-badge">2</span>
                <span class="card-title">Retriever</span>
              </div>
              <div class="card-body">
                <div class="config-row">
                  <div class="config-item">
                    <span class="config-label">TopK</span>
                    <span class="config-value">{{ ragConfig.topK }}</span>
                  </div>
                  <div class="config-item">
                    <span class="config-label">阈值</span>
                    <span class="config-value">{{ ragConfig.similarityThreshold }}</span>
                  </div>
                  <div class="config-item">
                    <span class="config-label">检索方式</span>
                    <span class="config-value method-tag">{{ currentRagTrace.search_method }}</span>
                  </div>
                </div>
                <div class="retrieved-list">
                  <div 
                    v-for="(item, idx) in currentRagTrace.retrieved_items" 
                    :key="idx"
                    class="retrieved-card"
                  >
                    <div class="score-indicator" :class="getScoreClass(item.score)">
                      {{ (item.score * 100).toFixed(0) }}%
                    </div>
                    <div class="retrieved-text">{{ item.question }}</div>
                  </div>
                  <div v-if="!currentRagTrace.retrieved_items?.length" class="empty-state">
                    <el-icon><Warning /></el-icon>
                    <span>未找到匹配的知识</span>
                  </div>
                </div>
              </div>
            </div>
            
            <!-- Context -->
            <div class="trace-card">
              <div class="card-header">
                <span class="step-badge">3</span>
                <span class="card-title">Context</span>
              </div>
              <div class="card-body">
                <div class="context-box" v-if="currentRagTrace.context_text">
                  {{ currentRagTrace.context_text }}
                </div>
                <div class="empty-state" v-else>
                  <el-icon><Warning /></el-icon>
                  <span>无命中片段，未注入上下文</span>
                </div>
              </div>
            </div>
            
            <!-- Confidence -->
            <div class="trace-card confidence-card">
              <div class="card-header">
                <span class="step-badge">4</span>
                <span class="card-title">置信度评估</span>
              </div>
              <div class="card-body">
                <div class="confidence-display">
                  <div class="confidence-circle" :class="getConfidenceClass(currentRagTrace.confidence)">
                    {{ (currentRagTrace.confidence * 100).toFixed(0) }}%
                  </div>
                  <div class="confidence-info">
                    <div class="confidence-level" :class="getConfidenceClass(currentRagTrace.confidence)">
                      {{ getConfidenceLevel(currentRagTrace.confidence) }}
                    </div>
                    <div class="confidence-action">
                      {{ getConfidenceAction(currentRagTrace.confidence) }}
                    </div>
                  </div>
                </div>
              </div>
            </div>
            
            <!-- Final Prompt -->
            <div class="trace-card">
              <div class="card-header clickable" @click="finalPromptExpanded = !finalPromptExpanded">
                <span class="step-badge">5</span>
                <span class="card-title">Final Prompt</span>
                <el-icon class="expand-icon" :class="{ expanded: finalPromptExpanded }">
                  <ArrowRight />
                </el-icon>
              </div>
              <div class="card-body" v-show="finalPromptExpanded">
                <div class="prompt-box" v-if="currentRagTrace.final_prompt">
                  {{ currentRagTrace.final_prompt }}
                </div>
                <div class="empty-state" v-else>
                  <el-icon><Warning /></el-icon>
                  <span>未记录发送给LLM的Prompt</span>
                </div>
              </div>
            </div>
          </template>
          
          <div v-else class="no-trace">
            <el-icon class="no-trace-icon"><Document /></el-icon>
            <span>该消息未保存 RAG 追溯信息</span>
          </div>
        </div>
        
        <!-- Edit Knowledge Button -->
        <el-tooltip
          content="暂无相关知识"
          placement="top"
          :disabled="hasRetrievedKnowledge"
        >
          <span class="edit-kb-btn-wrap">
            <el-button
              type="primary"
              :icon="Edit"
              class="edit-kb-btn"
              :disabled="!hasRetrievedKnowledge"
              @click="editKnowledge"
            >
              一键改知识
            </el-button>
          </span>
        </el-tooltip>
      </template>
      
      <el-empty v-else description="选择会话后可查看RAG追溯" :image-size="60" />
    </aside>

    <!-- 按时间检索对话框 -->
    <el-dialog
      v-model="searchDialogVisible"
      title="按时间段检索消息"
      width="460px"
    >
      <p style="margin-bottom: 12px; color: #606266;">选择要检索的时间范围：</p>
      <el-date-picker
        v-model="searchRange"
        type="daterange"
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        style="width: 100%;"
      />
      <template #footer>
        <el-button @click="searchDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="executeSearch">检索</el-button>
      </template>
    </el-dialog>

    <!-- 批量删除自定义日期范围对话框 -->
    <el-dialog
      v-model="batchDeleteDialogVisible"
      title="自定义时间段删除"
      width="460px"
    >
      <p style="margin-bottom: 12px; color: #606266;">选择要删除消息的日期范围：</p>
      <el-date-picker
        v-model="batchDeleteRange"
        type="daterange"
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        style="width: 100%;"
      />
      <template #footer>
        <el-button @click="batchDeleteDialogVisible = false">取消</el-button>
        <el-button type="danger" @click="confirmCustomDelete" :loading="batchDeleteLoading">确认删除</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="knowledgeEditVisible"
      title="编辑知识条目"
      width="720px"
      destroy-on-close
      @closed="resetKnowledgeEditForm"
    >
      <el-form label-width="88px" :disabled="knowledgeLoading">
        <el-form-item label="候选知识">
          <el-select
            v-model="selectedKnowledgeCandidateId"
            placeholder="选择检索到的知识"
            @change="onKnowledgeCandidateChange"
          >
            <el-option
              v-for="(item, idx) in retrievedKnowledgeCandidates"
              :key="item.id"
              :label="`候选 ${idx + 1} · 匹配度 ${(item.score * 100).toFixed(0)}% — ${item.question}`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="问题">
          <el-input v-model="knowledgeEditForm.question" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="答案">
          <el-input v-model="knowledgeEditForm.answer" type="textarea" :rows="8" />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="knowledgeEditForm.category" placeholder="请选择分类">
            <el-option v-for="c in knowledgeCategories" :key="c" :label="c" :value="c" />
          </el-select>
        </el-form-item>
        <el-form-item label="关键词">
          <div style="display:flex;gap:8px;margin-bottom:6px">
            <el-input v-model="knowledgeKwInput" placeholder="回车添加" style="width:200px" @keyup.enter="pushKnowledgeKw" />
            <el-button @click="pushKnowledgeKw">添加</el-button>
          </div>
          <div style="display:flex;flex-wrap:wrap;gap:4px">
            <el-tag v-for="(kw, i) in knowledgeEditForm.keywords" :key="kw" closable @close="knowledgeEditForm.keywords.splice(i, 1)">{{ kw }}</el-tag>
          </div>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="knowledgeEditVisible = false">取消</el-button>
        <el-button type="primary" :loading="knowledgeSaving || knowledgeLoading" @click="saveKnowledgeEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.workbench-container {
  display: flex;
  height: calc(100vh - 60px);
  margin: -20px;
  background-color: var(--el-bg-color-page);
}

/* Session Panel */
.session-panel {
  width: 340px;
  flex-shrink: 0;
  border-right: 1px solid var(--el-border-color-light);
  background-color: var(--el-bg-color);
  display: flex;
  flex-direction: column;
  padding: 16px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.panel-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.panel-header-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.search-hint {
  padding: 8px 12px;
  margin-bottom: 12px;
  background-color: #ecf5ff;
  color: #409eff;
  border-radius: 6px;
  font-size: 13px;
}

.status-filter {
  width: 100%;
  margin-bottom: 12px;
}

.session-list-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.session-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.session-section + .session-section {
  border-top: 1px solid var(--el-border-color-light);
}

.session-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 0 8px 8px;
}

.group-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  padding: 8px 12px;
  background-color: var(--el-bg-color);
  flex-shrink: 0;
}

.session-item {
  padding: 12px;
  border-radius: 8px;
  margin-bottom: 8px;
  cursor: pointer;
  background-color: var(--el-fill-color-light);
  transition: all 0.2s;
}

.session-item:hover {
  background-color: var(--el-fill-color);
}

.session-item.active {
  background-color: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-5);
}

.session-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}

.status-badge {
  color: white;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
}

.msg-count {
  color: var(--el-text-color-secondary);
  font-size: 11px;
}

.delete-btn {
  cursor: pointer;
  opacity: 0.6;
}

.delete-btn:hover {
  opacity: 1;
  color: var(--el-color-danger);
}

.timestamp {
  color: var(--el-text-color-secondary);
  font-size: 11px;
  margin-left: auto;
}

.session-title {
  font-weight: 500;
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.session-meta-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.session-confidence {
  color: var(--el-text-color-secondary);
  font-size: 11px;
}

.customer-tag {
  font-size: 11px;
  color: #8c8c8c;
  background: #f5f5f5;
  padding: 1px 6px;
  border-radius: 4px;
}

/* Conversation Panel */
.conversation-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 16px;
  min-width: 0;
  background-color: #ffffff;
}

.message-list {
  flex: 1;
  overflow-y: auto;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 16px;
  background-color: #ffffff;
}

.message-item {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}

.message-item.user,
.message-item.assistant,
.message-item.human {
  flex-direction: row;
}

.message-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

/* 用户头像 - 浅蓝色 */
.message-item.user .message-avatar {
  background-color: #e3f2fd;
  color: #1976d2;
}

/* AI助手头像 - 浅绿色 */
.message-item.assistant .message-avatar {
  background-color: #e8f5e9;
  color: #388e3c;
}

/* 人工客服头像 - 浅橙色 */
.message-item.human .message-avatar {
  background-color: #fff3e0;
  color: #f57c00;
}

.message-body {
  flex: 1;
  min-width: 0;
}

.message-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.role-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.message-content {
  font-size: 14px;
  line-height: 1.6;
  color: var(--el-text-color-primary);
  padding: 12px 16px;
  border-radius: 8px;
  white-space: pre-wrap;
  word-break: break-word;
}

/* 用户消息气泡 - 浅蓝灰色 */
.message-item.user .message-content {
  background-color: #f0f4f8;
}

/* AI助手消息气泡 - 浅绿灰色 */
.message-item.assistant .message-content {
  background-color: #f1f8f2;
}

/* 人工客服消息气泡 - 浅橙灰色 */
.message-item.human .message-content {
  background-color: #fef7f0;
}

.action-bar {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* RAG Panel */
.rag-panel {
  width: 320px;
  flex-shrink: 0;
  border-left: 1px solid var(--el-border-color-light);
  background-color: #fafbfc;
  display: flex;
  flex-direction: column;
  padding: 20px;
}

.msg-selector {
  width: 100%;
  margin-bottom: 16px;
}

.trace-content {
  flex: 1;
  overflow-y: auto;
  padding-right: 4px;
}

/* Trace Card */
.trace-card {
  background-color: #ffffff;
  border-radius: 12px;
  margin-bottom: 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  border: 1px solid #eef0f2;
  overflow: hidden;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border-bottom: 1px solid #f0f2f5;
  background-color: #fafbfc;
}

.card-header.clickable {
  cursor: pointer;
  user-select: none;
  transition: background-color 0.2s;
}

.card-header.clickable:hover {
  background-color: #f0f2f5;
}

.expand-icon {
  margin-left: auto;
  color: #9ca3af;
  transition: transform 0.2s;
}

.expand-icon.expanded {
  transform: rotate(90deg);
}

.step-badge {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  background-color: #e8f4fc;
  color: #1890ff;
  font-size: 12px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
}

.card-body {
  padding: 16px;
}

/* Query Row */
.query-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 12px;
}

.query-row:last-child {
  margin-bottom: 0;
}

.query-label {
  font-size: 11px;
  color: #9ca3af;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.query-text {
  font-size: 13px;
  color: #374151;
  line-height: 1.5;
  word-break: break-word;
}

.query-text.query-changed {
  color: #059669;
  font-weight: 500;
}

/* Rewrite diff */
.rewrite-diff {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.diff-removed {
  font-size: 12px;
  color: #dc2626;
  background: #fef2f2;
  padding: 2px 8px;
  border-radius: 4px;
  text-decoration: line-through;
}

.diff-added {
  font-size: 12px;
  color: #059669;
  background: #ecfdf5;
  padding: 2px 8px;
  border-radius: 4px;
}

/* Config Row */
.config-row {
  display: flex;
  gap: 12px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.config-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.config-label {
  font-size: 11px;
  color: #9ca3af;
}

.config-value {
  font-size: 13px;
  font-weight: 500;
  color: #374151;
}

.method-tag {
  background-color: #f3f4f6;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}

/* Retrieved List */
.retrieved-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.retrieved-card {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  background-color: #f9fafb;
  border-radius: 8px;
  border: 1px solid #f0f2f5;
}

.score-indicator {
  flex-shrink: 0;
  padding: 4px 8px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
}

.score-indicator.high {
  background-color: #ecfdf5;
  color: #059669;
}

.score-indicator.medium {
  background-color: #fffbeb;
  color: #d97706;
}

.score-indicator.low {
  background-color: #fef2f2;
  color: #dc2626;
}

.retrieved-text {
  font-size: 13px;
  color: #4b5563;
  line-height: 1.5;
  word-break: break-word;
}

/* Context Box */
.context-box {
  background-color: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px;
  font-size: 13px;
  color: #4b5563;
  line-height: 1.6;
  max-height: 150px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

/* Prompt Box */
.prompt-box {
  background-color: #f3f4f6;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px;
  font-size: 12px;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  color: #374151;
  line-height: 1.6;
  max-height: 200px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

/* Empty State */
.empty-state {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background-color: #fffbeb;
  border-radius: 8px;
  color: #92400e;
  font-size: 13px;
}

/* Confidence Card */
.confidence-display {
  display: flex;
  align-items: center;
  gap: 16px;
}

.confidence-circle {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 700;
  flex-shrink: 0;
}

.confidence-circle.high {
  background-color: #ecfdf5;
  color: #059669;
  border: 2px solid #a7f3d0;
}

.confidence-circle.medium {
  background-color: #fffbeb;
  color: #d97706;
  border: 2px solid #fde68a;
}

.confidence-circle.low {
  background-color: #fef2f2;
  color: #dc2626;
  border: 2px solid #fecaca;
}

.confidence-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.confidence-level {
  font-size: 15px;
  font-weight: 600;
}

.confidence-level.high {
  color: #059669;
}

.confidence-level.medium {
  color: #d97706;
}

.confidence-level.low {
  color: #dc2626;
}

.confidence-action {
  font-size: 13px;
  color: #6b7280;
}

/* No Trace */
.no-trace {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 40px 20px;
  color: #9ca3af;
  text-align: center;
}

.no-trace-icon {
  font-size: 40px;
  color: #d1d5db;
}

.edit-kb-btn {
  margin-top: 16px;
  width: 100%;
  border-radius: 8px;
  height: 40px;
}

.edit-kb-btn-wrap {
  display: inline-block;
  width: 100%;
}

/* Responsive */
@media (max-width: 1200px) {
  .rag-panel {
    width: 280px;
  }
}

@media (max-width: 992px) {
  .workbench-container {
    flex-direction: column;
  }
  
  .session-panel,
  .rag-panel {
    width: 100%;
    height: auto;
    max-height: 300px;
    border-right: none;
    border-left: none;
    border-bottom: 1px solid var(--el-border-color-light);
  }
}
</style>
