<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, ChatDotRound, User, Position } from '@element-plus/icons-vue'
import { getPendingConversations, getHandlingConversations, acceptConversation, closeConversation, sendHumanMessage } from '@/api/human'
import { getMessages } from '@/api/chat'
import type { Conversation, Message } from '@/types'

interface PendingConversationItem {
  id: string
  title: string
  status: string
  customer_id?: string
  updated_at: string
  message_count?: number
  wait_time_seconds?: number
}

// Pending conversations
const pendingList = ref<PendingConversationItem[]>([])
const pendingLoading = ref(false)

// Active conversations (being handled by current user)
const activeList = ref<Conversation[]>([])
const activeLoading = ref(false)

// Current conversation
const currentConversation = ref<Conversation | null>(null)
const messages = ref<Message[]>([])
const messagesLoading = ref(false)

// Message input
const messageInput = ref('')
const sending = ref(false)

// Message list ref for scrolling
const messageListRef = ref<HTMLElement | null>(null)

// 幂等去重缓存窗口（conversation_id:message_id）
const seenMessageIds = new Set<string>()
const SEEN_CACHE_MAX = 500

function markSeen(conversationId: string, messageId: number) {
  const key = `${conversationId}:${messageId}`
  seenMessageIds.add(key)
  if (seenMessageIds.size > SEEN_CACHE_MAX) {
    const iter = seenMessageIds.values()
    for (let i = 0; i < 100; i++) {
      const r = iter.next()
      if (r.done) break
      seenMessageIds.delete(r.value)
    }
  }
}

// 人工客服页面临时消息 ID 计数器（负数递减）
let _humanTempIdCounter = 0

// Load pending conversations
async function loadPendingConversations() {
  pendingLoading.value = true
  try {
    const response = await getPendingConversations()
    // API返回 { items, total, page, page_size }
    pendingList.value = response.data.items || []
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '加载待处理对话失败')
  } finally {
    pendingLoading.value = false
  }
}

// Load active conversations (only those handled by current agent)
async function loadActiveConversations() {
  activeLoading.value = true
  try {
    const response = await getHandlingConversations()
    activeList.value = response.data.items
  } catch (error: any) {
    console.error('Failed to load active conversations:', error)
  } finally {
    activeLoading.value = false
  }
}

// Load messages for current conversation
async function loadMessages() {
  if (!currentConversation.value) return
  
  messagesLoading.value = true
  try {
    const response = await getMessages(currentConversation.value.id, {
      page: 1,
      page_size: 100
    })
    messages.value = response.data.items
    // 标记所有已加载消息为已见
    for (const m of messages.value) {
      if (m.id && currentConversation.value) markSeen(currentConversation.value.id, m.id)
    }
    scrollToBottom()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '加载消息失败')
  } finally {
    messagesLoading.value = false
  }
}

// Select conversation
function selectConversation(conversation: Conversation) {
  currentConversation.value = conversation
  loadMessages()
  connectWebSocket(conversation.id)
  startMsgPolling()
}

// Accept pending conversation
async function handleAccept(conversation: PendingConversationItem) {
  try {
    await acceptConversation(conversation.id)
    ElMessage.success('已接入对话')
    await loadPendingConversations()
    await loadActiveConversations()
    // Find the accepted conversation in the active list
    const accepted = activeList.value.find(c => c.id === conversation.id)
    if (accepted) {
      selectConversation(accepted)
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '接入失败')
  }
}

// Close conversation
async function handleClose() {
  if (!currentConversation.value) return
  
  try {
    await closeConversation(currentConversation.value.id)
    ElMessage.success('已关闭人工服务')
    currentConversation.value = null
    messages.value = []
    stopMsgPolling()
    disconnectWebSocket()
    loadActiveConversations()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '关闭失败')
  }
}

// Send message
async function handleSend() {
  if (!currentConversation.value || !messageInput.value.trim()) return
  
  sending.value = true
  try {
    const content = messageInput.value.trim()
    messageInput.value = ''

    // Add message optimistically (negative temp ID, won't pollute since_id)
    const tempMessage: Message = {
      id: --_humanTempIdCounter,
      conversationId: currentConversation.value.id,
      role: 'human',
      content: content,
      timestamp: new Date().toISOString(),
      _isTemp: true,
    }
    messages.value.push(tempMessage)
    scrollToBottom()
    
    // Send via WebSocket if connected, otherwise via API
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'message',
        content: content
      }))
    } else {
      // Use human service API to send message with 'human' role
      await sendHumanMessage(currentConversation.value.id, content)
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '发送失败')
  } finally {
    sending.value = false
  }
}

// WebSocket connection (per-conversation)
let ws: WebSocket | null = null
let wsHeartbeatTimer: ReturnType<typeof setInterval> | null = null
const wsConnected = ref(false)
const wsReconnectCount = ref(0)
const wsConnecting = ref(false)

// Global WebSocket connection (cross-conversation notifications)
let globalWs: WebSocket | null = null
let globalWsHeartbeatTimer: ReturnType<typeof setInterval> | null = null
const globalWsConnected = ref(false)

// WS 推送未达提示：仅在两个通道都断开且不在首次连接中时显示
const showWsFallbackBar = computed(() => {
  if (!currentConversation.value) return false
  if (wsConnected.value || globalWsConnected.value) return false
  if (wsConnecting.value) return false
  return true
})

const wsStatusText = computed(() => {
  if (wsReconnectCount.value > 0) return `推送未达，轮询补偿中（重连 #${wsReconnectCount.value}）`
  return '推送未达，轮询补偿中'
})

function connectWebSocket(conversationId: string) {
  disconnectWebSocket()
  wsReconnectCount.value = 0
  wsConnecting.value = true
  
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const token = localStorage.getItem('token') || ''
  const wsUrl = `${protocol}//${window.location.host}/api/human/ws/${conversationId}?token=${token}`
  
  try {
    ws = new WebSocket(wsUrl)
    
    ws.onopen = () => {
      console.log('WebSocket connected')
      wsConnected.value = true
      wsConnecting.value = false
      wsReconnectCount.value = 0
      startWsHeartbeat()
      // WS 恢复后重启轮询（降低频率）
      startMsgPolling()
    }
    
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'pong' || data.type === 'connected') return
        
        if (data.type === 'message') {
          // 幂等去重：conversation_id + message_id
          const msgKey = `${conversationId}:${data.id}`
          if (data.id && seenMessageIds.has(msgKey)) return

          // 用 id 去重（优先），fallback 用 content+时间
          const existingById = data.id ? messages.value.findIndex(m => m.id === data.id) : -1
          if (existingById !== -1) return
          
          const existingByContent = messages.value.findIndex(m => 
            m.content === data.content && m.role === (data.role || 'user') &&
            Math.abs(new Date(m.timestamp).getTime() - new Date(data.timestamp || Date.now()).getTime()) < 5000
          )
          
          if (existingByContent === -1) {
            // 检查是否匹配一条临时消息（同 content + role + 时间窗口），就地替换 ID
            const tempMatch = messages.value.find(m =>
              m._isTemp && m.role === (data.role || 'user') && m.content === data.content &&
              Math.abs(new Date(m.timestamp).getTime() - new Date(data.timestamp || Date.now()).getTime()) < 5000
            )
            if (tempMatch && data.id) {
              tempMatch.id = data.id
              tempMatch._isTemp = false
              markSeen(conversationId, data.id)
            } else {
              const newMsg = {
                id: data.id || --_humanTempIdCounter,
                conversationId: conversationId,
                role: data.role || 'user',
                content: data.content,
                human_agent_name: data.human_agent_name,
                timestamp: data.timestamp || new Date().toISOString(),
                _isTemp: !data.id,
              }
              messages.value.push(newMsg)
              if (data.id) markSeen(conversationId, newMsg.id)
            }
            scrollToBottom()
          }
        } else if (data.type === 'status') {
          // 状态变更，刷新列表
          refreshAll()
        }
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e)
      }
    }
    
    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
    }
    
    ws.onclose = () => {
      console.log('WebSocket disconnected')
      wsConnected.value = false
      wsConnecting.value = false
      wsReconnectCount.value++
      stopWsHeartbeat()
      // WS 断开后加速轮询补偿
      startMsgPolling()
      // 自动重连（3 秒后）
      setTimeout(() => {
        if (currentConversation.value) {
          connectWebSocket(currentConversation.value.id)
        }
      }, 3000)
    }
  } catch (error) {
    console.error('Failed to connect WebSocket:', error)
  }
}

// ── 全局 WebSocket（跨对话事件通知） ──

function connectGlobalWebSocket() {
  disconnectGlobalWebSocket()

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const token = localStorage.getItem('token') || ''
  if (!token) return
  const wsUrl = `${protocol}//${window.location.host}/api/human/ws?token=${token}`

  try {
    globalWs = new WebSocket(wsUrl)

    globalWs.onopen = () => {
      globalWsConnected.value = true
      startGlobalWsHeartbeat()
    }

    globalWs.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'pong' || data.type === 'connected') return
        handleGlobalWsEvent(data)
      } catch { /* ignore */ }
    }

    globalWs.onerror = () => {}

    globalWs.onclose = () => {
      globalWsConnected.value = false
      stopGlobalWsHeartbeat()
      // 自动重连（3 秒后）
      setTimeout(() => connectGlobalWebSocket(), 3000)
    }
  } catch {
    setTimeout(() => connectGlobalWebSocket(), 3000)
  }
}

function disconnectGlobalWebSocket() {
  stopGlobalWsHeartbeat()
  if (globalWs) {
    globalWs.close()
    globalWs = null
  }
  globalWsConnected.value = false
}

function startGlobalWsHeartbeat() {
  stopGlobalWsHeartbeat()
  globalWsHeartbeatTimer = setInterval(() => {
    if (globalWs && globalWs.readyState === WebSocket.OPEN) {
      globalWs.send(JSON.stringify({ type: 'ping' }))
    }
  }, 25000)
}

function stopGlobalWsHeartbeat() {
  if (globalWsHeartbeatTimer) { clearInterval(globalWsHeartbeatTimer); globalWsHeartbeatTimer = null }
}

function handleGlobalWsEvent(data: any) {
  if (data.type === 'new_pending') {
    // 新的待处理对话 → 刷新 pending 列表
    loadPendingConversations()
  } else if (data.type === 'new_message') {
    // 某个对话有新消息
    const convId = data.conversation_id
    if (currentConversation.value && currentConversation.value.id === convId) {
      // 当前选中的对话：追加消息（幂等去重）
      const msg = data.message
      if (msg && msg.id) {
        const key = `${convId}:${msg.id}`
        if (seenMessageIds.has(key) || messages.value.some(m => m.id === msg.id)) return
        // fallback: content+时间去重（防止乐观渲染的临时 ID 不匹配）
        const dupByContent = messages.value.some(m =>
          m.content === msg.content && m.role === msg.role &&
          Math.abs(new Date(m.timestamp).getTime() - new Date(msg.timestamp || Date.now()).getTime()) < 5000
        )
        if (!dupByContent) {
          // 检查是否匹配一条临时消息，就地替换 ID
          const tempMatch = messages.value.find(m =>
            m._isTemp && m.role === msg.role && m.content === msg.content &&
            Math.abs(new Date(m.timestamp).getTime() - new Date(msg.timestamp || Date.now()).getTime()) < 5000
          )
          if (tempMatch && msg.id) {
            tempMatch.id = msg.id
            tempMatch._isTemp = false
            markSeen(convId, msg.id)
          } else {
            messages.value.push({
              id: msg.id || --_humanTempIdCounter,
              conversationId: convId,
              role: msg.role,
              content: msg.content,
              human_agent_name: msg.human_agent_name,
              timestamp: msg.timestamp || new Date().toISOString(),
              _isTemp: !msg.id,
            })
            if (msg.id) markSeen(convId, msg.id)
          }
          scrollToBottom()
        }
      }
    }
    // 无论是否当前对话，刷新活跃列表以更新消息计数
    loadActiveConversations()
  } else if (data.type === 'status_change') {
    // 对话状态变更 → 刷新两个列表
    loadPendingConversations()
    loadActiveConversations()
    // 如果是当前对话被关闭，清空选中
    if (currentConversation.value && currentConversation.value.id === data.conversation_id) {
      if (data.status === 'human_closed' || data.status === 'normal') {
        currentConversation.value = null
        messages.value = []
        stopMsgPolling()
        disconnectWebSocket()
      }
    }
  }
}

// ── 对话级 WebSocket ──

function startWsHeartbeat() {
  stopWsHeartbeat()
  wsHeartbeatTimer = setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'ping' }))
    }
  }, 25000)
}

function stopWsHeartbeat() {
  if (wsHeartbeatTimer) { clearInterval(wsHeartbeatTimer); wsHeartbeatTimer = null }
}

function disconnectWebSocket() {
  stopWsHeartbeat()
  if (ws) {
    // 清除回调，避免 close 事件触发重连计数和自动重连
    ws.onclose = null
    ws.onerror = null
    ws.onmessage = null
    ws.onopen = null
    ws.close()
    ws = null
  }
  wsConnected.value = false
  wsConnecting.value = false
}

// Scroll to bottom of message list
function scrollToBottom() {
  nextTick(() => {
    if (messageListRef.value) {
      messageListRef.value.scrollTop = messageListRef.value.scrollHeight
    }
  })
}

// Format time
function formatTime(timestamp: string): string {
  const date = new Date(timestamp)
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Shanghai' })
}

// Get status text
function getStatusText(status: string): string {
  const statusMap: Record<string, string> = {
    'normal': '正常',
    'pending_human': '等待接入',
    'human_handling': '处理中',
    'human_closed': '已关闭'
  }
  return statusMap[status] || status
}

// Get status type
function getStatusType(status: string): string {
  const typeMap: Record<string, string> = {
    'normal': 'info',
    'pending_human': 'warning',
    'human_handling': 'success',
    'human_closed': 'info'
  }
  return typeMap[status] || 'info'
}

// Format customer_id for display
function formatCustomerId(customerId: string): string {
  if (!customerId || customerId === 'anonymous') return '匿名用户'
  if (customerId.startsWith('visitor_')) return `访客 ${customerId.slice(8, 14)}`
  if (customerId.startsWith('user_')) return `用户 #${customerId.slice(5)}`
  return customerId
}

// Refresh all
function refreshAll() {
  loadPendingConversations()
  loadActiveConversations()
}

// Auto refresh
let refreshInterval: number | null = null
let msgPollInterval: number | null = null

function startMsgPolling() {
  stopMsgPolling()
  if (!currentConversation.value) return
  // WS 连接时降低轮询频率（作为保底），未连接时 2 秒快速补拉
  const interval = wsConnected.value ? 10000 : 2000
  msgPollInterval = window.setInterval(async () => {
    if (!currentConversation.value || sending.value) return
    try {
      // 增量拉取：使用 since_id（仅基于已确认的正数 ID）
      const confirmedIds = messages.value.filter(m => m.id > 0).map(m => m.id)
      const lastId = confirmedIds.length > 0
        ? Math.max(...confirmedIds)
        : undefined
      const params: any = lastId
        ? { since_id: lastId }
        : { page: 1, page_size: 100 }
      const response = await getMessages(currentConversation.value.id, params)
      const newMessages = response.data.items
      if (newMessages.length > 0) {
        if (lastId) {
          // 增量追加，幂等去重
          for (const msg of newMessages) {
            const key = `${currentConversation.value!.id}:${msg.id}`
            if (!seenMessageIds.has(key) && !messages.value.some(m => m.id === msg.id)) {
              messages.value.push(msg)
              markSeen(currentConversation.value!.id, msg.id)
            }
          }
          scrollToBottom()
        } else {
          messages.value = newMessages
          scrollToBottom()
        }
      }
    } catch { /* ignore */ }
  }, interval)
}

function stopMsgPolling() {
  if (msgPollInterval) { clearInterval(msgPollInterval); msgPollInterval = null }
}

onMounted(() => {
  refreshAll()
  // 全局 WebSocket：接收跨对话事件通知
  connectGlobalWebSocket()
  // 30秒保底刷新（全局 WS 正常时仅作为兜底）
  refreshInterval = window.setInterval(refreshAll, 30000)
})

onUnmounted(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
  stopMsgPolling()
  disconnectWebSocket()
  disconnectGlobalWebSocket()
})
</script>

<template>
  <div class="human-service-container">
    <!-- Sidebar -->
    <aside class="sidebar">
      <!-- Pending Section -->
      <div class="sidebar-section">
        <div class="section-header">
          <span>待处理对话</span>
          <el-button text :icon="Refresh" size="small" @click="loadPendingConversations" />
        </div>
        <div class="conversation-list" v-loading="pendingLoading">
          <div
            v-for="conv in pendingList"
            :key="conv.id"
            class="conversation-item pending"
          >
            <div class="conv-info">
              <div class="conv-title">{{ conv.title }}</div>
              <div class="conv-meta">
                <el-tag :type="getStatusType(conv.status)" size="small">
                  {{ getStatusText(conv.status) }}
                </el-tag>
                <span class="customer-tag" v-if="conv.customer_id">{{ formatCustomerId(conv.customer_id) }}</span>
              </div>
            </div>
            <el-button type="primary" size="small" @click="handleAccept(conv)">
              接入
            </el-button>
          </div>
          <el-empty v-if="pendingList.length === 0" description="暂无待处理对话" :image-size="60" />
        </div>
      </div>

      <!-- Active Section -->
      <div class="sidebar-section">
        <div class="section-header">
          <span>我的对话</span>
          <el-button text :icon="Refresh" size="small" @click="loadActiveConversations" />
        </div>
        <div class="conversation-list" v-loading="activeLoading">
          <div
            v-for="conv in activeList"
            :key="conv.id"
            class="conversation-item"
            :class="{ active: currentConversation?.id === conv.id }"
            @click="selectConversation(conv)"
          >
            <div class="conv-info">
              <div class="conv-title">{{ conv.title }}</div>
              <div class="conv-meta">
                <el-tag type="success" size="small">处理中</el-tag>
                <span class="customer-tag" v-if="conv.customer_id">{{ formatCustomerId(conv.customer_id) }}</span>
              </div>
            </div>
          </div>
          <el-empty v-if="activeList.length === 0" description="暂无进行中的对话" :image-size="60" />
        </div>
      </div>
    </aside>

    <!-- Main Chat Area -->
    <main class="chat-main">
      <template v-if="currentConversation">
        <!-- Chat Header -->
        <div class="chat-header">
          <div class="header-info">
            <el-icon><ChatDotRound /></el-icon>
            <span class="conv-title">{{ currentConversation.title }}</span>
            <el-tag type="success" size="small">处理中</el-tag>
            <span class="customer-tag" v-if="currentConversation.customer_id">{{ formatCustomerId(currentConversation.customer_id) }}</span>
          </div>
          <el-button type="danger" size="small" @click="handleClose">
            关闭服务
          </el-button>
        </div>

        <!-- WS 推送未达提示 -->
        <div v-if="showWsFallbackBar" class="ws-fallback-bar">
          ⚠️ {{ wsStatusText }}
        </div>

        <!-- Message List -->
        <div class="message-list" ref="messageListRef" v-loading="messagesLoading">
          <div
            v-for="msg in messages"
            :key="msg.id"
            class="message-item"
            :class="msg.role"
          >
            <div class="message-avatar">
              <el-icon v-if="msg.role === 'user'"><User /></el-icon>
              <el-icon v-else-if="msg.role === 'human'"><Position /></el-icon>
              <el-icon v-else><ChatDotRound /></el-icon>
            </div>
            <div class="message-content">
              <div class="message-header">
                <span class="role-name">
                  {{ msg.role === 'user' ? '客户' : msg.role === 'human' ? (msg.human_agent_name ? `客服 · ${msg.human_agent_name}` : '客服') : 'AI助手' }}
                </span>
                <span class="message-time">{{ formatTime(msg.timestamp) }}</span>
              </div>
              <div class="message-text">{{ msg.content }}</div>
            </div>
          </div>
          <el-empty v-if="messages.length === 0" description="暂无消息" :image-size="80" />
        </div>

        <!-- Message Input -->
        <div class="message-input">
          <el-input
            v-model="messageInput"
            type="textarea"
            :rows="2"
            placeholder="输入消息..."
            @keyup.ctrl.enter="handleSend"
          />
          <el-button
            type="primary"
            :loading="sending"
            :disabled="!messageInput.trim()"
            @click="handleSend"
          >
            发送
          </el-button>
        </div>
      </template>

      <!-- Empty State -->
      <el-empty v-else description="选择一个对话开始服务" :image-size="120" />
    </main>
  </div>
</template>

<style scoped>
.human-service-container {
  display: flex;
  height: calc(100vh - 60px);
  margin: -20px;
  background-color: #ffffff;
}

.sidebar {
  width: 320px;
  flex-shrink: 0;
  border-right: 1px solid var(--el-border-color-light);
  background-color: #fafafa;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-bottom: 1px solid var(--el-border-color-light);
}

.sidebar-section:last-child {
  border-bottom: none;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  border-bottom: 1px solid var(--el-border-color-lighter);
  background-color: #ffffff;
}

.conversation-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.conversation-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background-color 0.2s;
  background-color: #ffffff;
  margin-bottom: 6px;
}

.conversation-item:hover {
  background-color: #f5f5f5;
}

.conversation-item.active {
  background-color: #e8f4fc;
  border: 1px solid #d0e8f7;
}

.conversation-item.pending {
  background-color: #fef8e8;
  border: 1px solid #f5e6c4;
}

.conv-info {
  flex: 1;
  min-width: 0;
}

.conv-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 4px;
}

.conv-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.customer-tag {
  font-size: 11px;
  color: #8c8c8c;
  background: #f5f5f5;
  padding: 1px 6px;
  border-radius: 4px;
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background-color: #ffffff;
}

.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--el-border-color-light);
  background-color: #ffffff;
}

.header-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-info .conv-title {
  font-size: 16px;
  font-weight: 500;
}

.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  background-color: #ffffff;
}

.message-item {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}

.message-item.user {
  flex-direction: row;
}

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

/* 客户头像 - 浅蓝色 */
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

.message-content {
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

.message-time {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.message-text {
  font-size: 14px;
  line-height: 1.6;
  color: var(--el-text-color-primary);
  padding: 12px 16px;
  border-radius: 8px;
  white-space: pre-wrap;
  word-break: break-word;
}

/* 客户消息气泡 - 浅蓝灰色 */
.message-item.user .message-text {
  background-color: #f0f4f8;
}

/* AI助手消息气泡 - 浅绿灰色 */
.message-item.assistant .message-text {
  background-color: #f1f8f2;
}

/* 人工客服消息气泡 - 浅橙灰色 */
.message-item.human .message-text {
  background-color: #fef7f0;
}

.message-input {
  display: flex;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid var(--el-border-color-light);
  background-color: #ffffff;
}

.message-input .el-textarea {
  flex: 1;
}

.message-input .el-button {
  align-self: flex-end;
}

/* WS 推送未达提示条 */
.ws-fallback-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 20px;
  background: #fff7e6;
  border-bottom: 1px solid #ffe58f;
  font-size: 12px;
  color: #ad6800;
}

/* Responsive */
@media (max-width: 768px) {
  .human-service-container {
    flex-direction: column;
  }
  
  .sidebar {
    width: 100%;
    height: 200px;
    flex-direction: row;
    border-right: none;
    border-bottom: 1px solid var(--el-border-color-light);
  }
  
  .sidebar-section {
    flex: 1;
    border-bottom: none;
    border-right: 1px solid var(--el-border-color-light);
  }
  
  .sidebar-section:last-child {
    border-right: none;
  }
}
</style>
