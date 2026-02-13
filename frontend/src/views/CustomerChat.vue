<template>
  <div class="customer-chat-container">
    <!-- 头部 -->
    <header class="chat-header">
      <div class="header-left">
        <div class="brand">
          <el-icon :size="22"><Service /></el-icon>
          <span class="title">智能客服</span>
        </div>
        <el-tag v-if="currentConversationStatus === 'human_handling'" type="warning" size="small" effect="plain" round>
          人工服务中
        </el-tag>
        <el-tag v-else-if="currentConversationStatus === 'pending_human'" size="small" effect="plain" round>
          等待人工接入
        </el-tag>
      </div>
      <div class="header-right">
        <template v-if="isStaffUser">
          <el-button text bg size="small" @click="goToAdmin">进入后台</el-button>
        </template>
        <template v-else-if="isCustomerUser">
          <span class="user-name">{{ (authStore.user as any)?.display_name || authStore.user?.username }}</span>
          <el-button text bg size="small" @click="handleLogout">退出</el-button>
        </template>
        <template v-else>
          <el-button text bg size="small" @click="goToLogin">登录</el-button>
        </template>
      </div>
    </header>

    <!-- 聊天区域 -->
    <main class="chat-main">
      <!-- 对话列表侧边栏 -->
      <aside class="conversation-sidebar" :class="{ collapsed: sidebarCollapsed }">
        <div class="sidebar-header">
          <span v-if="!sidebarCollapsed" class="sidebar-title">历史对话</span>
          <el-button
            :icon="sidebarCollapsed ? 'Expand' : 'Fold'"
            text
            size="small"
            @click="sidebarCollapsed = !sidebarCollapsed"
          />
        </div>
        <div v-if="!sidebarCollapsed" class="conversation-list">
          <div
            v-for="conv in conversations"
            :key="conv.id"
            class="conversation-item"
            :class="{ active: currentConversationId === conv.id }"
            @click="selectConversation(conv.id)"
          >
            <el-icon class="conv-icon" :size="16"><ChatDotRound /></el-icon>
            <span class="conv-title">{{ conv.title || '新对话' }}</span>
            <el-button
              class="delete-btn"
              :icon="Delete"
              text
              size="small"
              @click.stop="deleteConversation(conv.id)"
            />
          </div>
        </div>
        <div v-if="!sidebarCollapsed" class="sidebar-footer">
          <el-button type="primary" plain @click="createNewConversation" :icon="Plus" style="width:100%">
            新对话
          </el-button>
        </div>
      </aside>

      <!-- 消息区域 -->
      <div class="message-area">
        <div class="messages-container" ref="messagesContainer">
          <!-- 空状态 -->
          <div v-if="messages.length === 0" class="empty-state">
            <div class="empty-icon-wrap">
              <el-icon :size="40"><Service /></el-icon>
            </div>
            <h3 class="empty-title">您好，有什么可以帮您？</h3>
            <p class="empty-desc">我是智能客服助手，可以为您解答商品、订单、物流等问题</p>
            <div class="quick-questions">
              <div
                v-for="q in quickQuestions"
                :key="q"
                class="quick-item"
                @click="sendQuickQuestion(q)"
              >
                {{ q }}
              </div>
            </div>
          </div>

          <!-- 消息列表 -->
          <div v-else class="messages-list">
            <div
              v-for="msg in messages"
              :key="msg.id"
              class="message-row"
              :class="msg.role"
            >
              <div class="avatar" :class="msg.role">
                <el-icon v-if="msg.role === 'user'" :size="18"><User /></el-icon>
                <el-icon v-else-if="msg.role === 'human'" :size="18"><Headset /></el-icon>
                <el-icon v-else :size="18"><Service /></el-icon>
              </div>
              <div class="bubble-wrap">
                <div class="bubble-header">
                  <span class="role-name">{{ getRoleLabel(msg) }}</span>
                  <span class="msg-time">{{ formatTime(msg.timestamp) }}</span>
                  <el-button
                    v-if="canDeleteMessage(msg)"
                    class="msg-delete-btn"
                    :icon="Delete"
                    text
                    size="small"
                    @click.stop="deleteMessage(msg.id)"
                  />
                </div>
                <div class="bubble" :class="msg.role" v-html="renderMarkdown(msg.content)"></div>

              </div>
            </div>

            <!-- 加载动画：仅在发送消息且AI尚未开始输出内容时显示 -->
            <div v-if="showTypingIndicator" class="message-row assistant">
              <div class="avatar assistant">
                <el-icon :size="18"><Service /></el-icon>
              </div>
              <div class="bubble-wrap">
                <div class="bubble assistant typing-bubble">
                  <div class="typing-indicator">
                    <span class="dot"></span>
                    <span class="dot"></span>
                    <span class="dot"></span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 低置信度转人工提示 -->
        <div v-if="suggestHuman && currentConversationStatus === 'normal'" class="suggest-bar">
          <el-icon :size="16"><WarningFilled /></el-icon>
          <span>AI 对上一个问题的回答可能不够准确</span>
          <el-button type="warning" size="small" plain round @click="transferToHuman">
            转人工客服
          </el-button>
        </div>

        <!-- 输入区域 -->
        <div class="input-area">
          <div class="input-box">
            <el-input
              v-model="inputMessage"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              placeholder="输入您的问题，按 Enter 发送..."
              resize="none"
              @keydown.enter.exact.prevent="sendMessage"
              @focus="isInputFocused = true"
              @blur="isInputFocused = false"
              :disabled="chatStore.isSending"
            />
          </div>
          <div class="input-actions">
            <el-button
              v-if="currentConversationStatus === 'normal'"
              :icon="Headset"
              text
              @click="transferToHuman"
              :disabled="chatStore.isSending || !currentConversationId"
            >
              转人工
            </el-button>
            <el-button
              type="primary"
              :icon="Promotion"
              @click="sendMessage"
              :disabled="chatStore.isSending || !inputMessage.trim()"
              round
            >
              发送
            </el-button>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import {
  ChatDotRound, User, Service, Delete, Plus, Promotion, Headset, WarningFilled
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'
import { getGuestToken } from '@/api/auth'
import { ChatWebSocket, buildWsUrl } from '@/utils/websocket'
import { renderSafeMarkdown } from '@/utils/safeMarkdown'
import {
  getOrCreateGuestDeviceId,
  rememberGuestConversationIds,
  removeGuestConversationId,
} from '@/utils/guestIdentity'

const GUEST_TOKEN_KEY = 'guest_token'
const VISITOR_ID_KEY = 'visitor_id'

const router = useRouter()
const authStore = useAuthStore()
const chatStore = useChatStore()

const sidebarCollapsed = ref(false)
const inputMessage = ref('')
const messagesContainer = ref<HTMLElement | null>(null)
const isInputFocused = ref(false)

const isStaffUser = computed(() => authStore.user && (authStore.user.role === 'admin' || authStore.user.role === 'cs'))
const isCustomerUser = computed(() => authStore.user && authStore.user.role === 'customer')
const conversations = computed(() => chatStore.conversations)
const currentConversationId = computed(() => chatStore.currentConversation?.id)
const currentConversationStatus = computed(() => chatStore.currentConversation?.status || 'normal')
const messages = computed(() => chatStore.sortedMessages)
const suggestHuman = computed(() => chatStore.suggestHuman)

/** 仅在发送消息且AI尚未开始输出内容时显示typing indicator */
const showTypingIndicator = computed(() => {
  if (!chatStore.isSending) return false
  // 如果最后一条消息是 assistant 且已有内容（SSE 正在流式输出），不显示
  const msgs = chatStore.sortedMessages
  if (msgs.length > 0) {
    const last = msgs[msgs.length - 1]
    if (last.role === 'assistant' && last.content && last.content.length > 0) {
      return false
    }
  }
  return true
})

/** Ensure a guest token exists in localStorage (for anonymous visitors) */
async function ensureGuestToken() {
  if (authStore.user) return

  getOrCreateGuestDeviceId()

  const existing = localStorage.getItem(GUEST_TOKEN_KEY)
  if (existing) {
    authStore.setToken(existing)
    return
  }

  try {
    const res = await getGuestToken()
    const { access_token, visitor_id } = res.data
    localStorage.setItem(GUEST_TOKEN_KEY, access_token)
    localStorage.setItem(VISITOR_ID_KEY, visitor_id)
    authStore.setToken(access_token)
  } catch (e) {
    console.error('Failed to get guest token:', e)
  }
}
const quickQuestions = [
  '如何申请退货退款？',
  '我的订单什么时候发货？',
  '物流信息在哪里查看？',
  '有什么优惠活动吗？',
  '商品尺码怎么选择？',
  '支持哪些支付方式？',
  '如何联系人工客服？',
  '商品质量有保障吗？'
]

function getRoleLabel(msg: any): string {
  if (msg.role === 'user') return '我'
  if (msg.role === 'human') return msg.human_agent_name ? `人工客服 · ${msg.human_agent_name}` : '人工客服'
  return 'AI 客服'
}

// --- WebSocket 实时通信 ---
let chatWs: ChatWebSocket | null = null
let wsConnected = ref(false)

function connectChatWebSocket() {
  disconnectChatWebSocket()
  const token = localStorage.getItem(GUEST_TOKEN_KEY) || localStorage.getItem('token') || ''
  if (!token) return

  chatWs = new ChatWebSocket({
    reconnectInterval: 3000,
    maxReconnects: -1, // 无限重连
    heartbeatInterval: 25000,
    onConnected: () => {
      wsConnected.value = true
      console.log('Chat WebSocket connected')
      // 注册 WS 发送回调供 store 使用（人工模式优先走 WS）
      chatStore.setWsSender((data: any) => {
        if (chatWs?.isConnected) {
          chatWs.send(data)
          return true
        }
        return false
      })
      // WS 恢复后重启轮询（降低频率）
      startMsgPolling()
    },
    onDisconnected: () => {
      wsConnected.value = false
      chatStore.setWsSender(null)
      // WS 断开后加速轮询补偿
      startMsgPolling()
    },
    onMessage: (data: any) => {
      handleWsMessage(data)
    },
  })

  chatWs.connect(buildWsUrl('/api/chat/ws', token))
}

function disconnectChatWebSocket() {
  if (chatWs) {
    chatWs.disconnect()
    chatWs = null
  }
  wsConnected.value = false
  chatStore.setWsSender(null)
}

function handleWsMessage(data: any) {
  if (data.type === 'message') {
    // 收到新消息（人工客服回复或自己发送的确认）
    const convId = data.conversation_id
    if (convId && currentConversationId.value === convId) {
      // 幂等去重：conversation_id + message_id
      if (data.id && chatStore.isMessageSeen(convId, data.id)) return
      // fallback 内容去重
      const exists = chatStore.messages.some(m =>
        m.id === data.id ||
        (m.content === data.content && m.role === data.role &&
         Math.abs(new Date(m.timestamp).getTime() - new Date(data.timestamp || Date.now()).getTime()) < 3000)
      )
      if (!exists) {
        // 如果 WS 推送的消息匹配一条临时消息（同 content + role + 时间窗口），就地替换 ID
        const tempMatch = chatStore.messages.find(m =>
          m._isTemp && m.role === data.role && m.content === data.content &&
          Math.abs(new Date(m.timestamp).getTime() - new Date(data.timestamp || Date.now()).getTime()) < 5000
        )
        if (tempMatch && data.id) {
          chatStore.replaceMessageId(tempMatch.id, data.id)
        } else {
          chatStore.addMessage({
            id: data.id || chatStore.nextTempId(),
            conversationId: convId,
            role: data.role,
            content: data.content,
            human_agent_name: data.human_agent_name,
            timestamp: data.timestamp || new Date().toISOString(),
            _isTemp: !data.id,
          })
        }
      }
    }
  } else if (data.type === 'status') {
    // 对话状态变更
    const convId = data.conversation_id
    if (convId) {
      chatStore.updateConversation(convId, { status: data.status })
    }
  }
}

// --- 降级轮询（仅在 WebSocket 未连接时使用） ---
let convListTimer: ReturnType<typeof setInterval> | null = null
let msgPollTimer: ReturnType<typeof setInterval> | null = null

function startConvListPolling() {
  stopConvListPolling()
  convListTimer = setInterval(async () => {
    if (isInputFocused.value) return
    try { await chatStore.fetchConversations() } catch { /* ignore */ }
  }, 15000)
}
function stopConvListPolling() {
  if (convListTimer) { clearInterval(convListTimer); convListTimer = null }
}

/** 静默刷新消息：增量拉取 since_id 之后的新消息 */
async function silentFetchMessages() {
  if (!currentConversationId.value) return
  if (chatStore.isSending || chatStore.isStreaming) return
  if (isInputFocused.value) return
  try {
    const { getMessages: fetchMsgs } = await import('@/api/chat')
    // 计算当前最大已确认消息 ID（仅正数），避免临时 ID 污染 since_id
    const lastId = chatStore.maxConfirmedId > 0 ? chatStore.maxConfirmedId : undefined
    const params: any = lastId
      ? { since_id: lastId }
      : { page: 1, page_size: 100 }
    const response = await fetchMsgs(currentConversationId.value!, params)
    const newItems = response.data.items
    if (newItems.length > 0) {
      if (lastId) {
        // 增量追加：只添加新消息
        for (const item of newItems) {
          const exists = chatStore.messages.some(m => m.id === item.id)
          if (!exists) {
            chatStore.addMessage(item)
          }
        }
      } else {
        // 首次全量加载
        chatStore.setMessages(newItems)
      }
    }
  } catch { /* ignore */ }
}

function startMsgPolling() {
  stopMsgPolling()
  // WS 正常时 30 秒保底兜底，WS 断开时 2 秒快速补拉
  const interval = wsConnected.value ? 30000 : 2000
  msgPollTimer = setInterval(async () => {
    // WebSocket 连接正常时跳过轮询（消息已通过 WS 实时推送）
    if (wsConnected.value) return
    await silentFetchMessages()
  }, interval)
}
function stopMsgPolling() {
  if (msgPollTimer) { clearInterval(msgPollTimer); msgPollTimer = null }
}

onMounted(async () => {
  const hasGuestToken = !!localStorage.getItem(GUEST_TOKEN_KEY)
  if (authStore.token && !authStore.user && !hasGuestToken) {
    await authStore.fetchCurrentUser()
  }

  await ensureGuestToken()
  await chatStore.fetchConversations()
  if (!authStore.user) {
    rememberGuestConversationIds(conversations.value.map((c: any) => c.id))
  }
  if (conversations.value.length > 0) {
    chatStore.setCurrentConversation(conversations.value[0])
    await chatStore.fetchMessages(conversations.value[0].id)
  }
  // 建立 WebSocket 连接
  connectChatWebSocket()
  // 对话列表仍用轮询（频率降低）
  startConvListPolling()
  // 消息轮询作为降级保底
  startMsgPolling()
})

onUnmounted(() => {
  disconnectChatWebSocket()
  stopConvListPolling()
  stopMsgPolling()
})

watch(messages, () => { nextTick(() => scrollToBottom()) })

function scrollToBottom() {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

function goToAdmin() {
  router.push('/workbench')
}

function goToLogin() {
  // Clear guest token so the router guard doesn't redirect back
  // Keep visitor_id so it can be used for conversation migration after login
  localStorage.removeItem(GUEST_TOKEN_KEY)
  authStore.clearAuth()
  router.push('/login')
}

async function handleLogout() {
  disconnectChatWebSocket()
  stopConvListPolling()
  stopMsgPolling()
  authStore.clearAuth()
  localStorage.removeItem(GUEST_TOKEN_KEY)
  localStorage.removeItem(VISITOR_ID_KEY)
  await ensureGuestToken()
  connectChatWebSocket()
  await chatStore.fetchConversations()
  if (conversations.value.length > 0) {
    chatStore.setCurrentConversation(conversations.value[0])
    await chatStore.fetchMessages(conversations.value[0].id)
  } else {
    chatStore.setCurrentConversation(null as any)
  }
  startConvListPolling()
  startMsgPolling()
}

async function createNewConversation() {
  const conv = await chatStore.createNewConversation()
  if (!authStore.user && conv?.id) {
    rememberGuestConversationIds([conv.id])
  }
}

async function selectConversation(id: string) {
  const conv = conversations.value.find(c => c.id === id)
  if (conv) {
    chatStore.setCurrentConversation(conv)
    await chatStore.fetchMessages(id)
  }
}

async function deleteConversation(id: string) {
  try {
    await ElMessageBox.confirm('确定要删除这个对话吗？', '提示', { type: 'warning' })
    await chatStore.deleteConversationById(id)
    if (!authStore.user) {
      removeGuestConversationId(id)
    }
  } catch { /* cancelled */ }
}

function canDeleteMessage(msg: any) {
  return isCustomerUser.value && msg.role === 'user'
}

async function deleteMessage(messageId: number) {
  if (!currentConversationId.value) return
  try {
    await ElMessageBox.confirm('确定删除这条消息吗？', '提示', { type: 'warning' })
    await chatStore.deleteMessageById(messageId)
  } catch {
    // cancelled
  }
}

async function sendMessage() {
  const content = inputMessage.value.trim()
  if (!content || chatStore.isSending) return
  if (!currentConversationId.value) await chatStore.createNewConversation()
  inputMessage.value = ''
  await chatStore.sendMessageWithStream(content)
}

function sendQuickQuestion(question: string) {
  inputMessage.value = question
  sendMessage()
}

async function transferToHuman() {
  if (!currentConversationId.value) return
  try {
    await ElMessageBox.confirm('确定要转接人工客服吗？', '提示', { type: 'info' })
    await chatStore.transferToHumanService()
  } catch { /* cancelled */ }
}

function formatTime(timestamp: string) {
  return new Date(timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Shanghai' })
}

function renderMarkdown(content: string) {
  return renderSafeMarkdown(content)
}
</script>

<style scoped>
/* ===== Layout ===== */
.customer-chat-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f0f2f5;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

/* ===== Header ===== */
.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 24px;
  height: 56px;
  background: #fff;
  border-bottom: 1px solid #e8e8e8;
  flex-shrink: 0;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #1677ff;
}
.brand .title {
  font-size: 17px;
  font-weight: 600;
  color: #1d2129;
}
.user-name {
  font-size: 13px;
  color: #595959;
  margin-right: 4px;
}

/* ===== Main ===== */
.chat-main {
  flex: 1;
  display: flex;
  overflow: hidden;
}

/* ===== Sidebar ===== */
.conversation-sidebar {
  width: 260px;
  background: #fff;
  border-right: 1px solid #e8e8e8;
  display: flex;
  flex-direction: column;
  transition: width 0.25s ease;
  flex-shrink: 0;
}
.conversation-sidebar.collapsed {
  width: 48px;
}
.sidebar-header {
  padding: 14px 12px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #f0f0f0;
}
.sidebar-title {
  font-size: 14px;
  font-weight: 600;
  color: #1d2129;
}
.conversation-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}
.conversation-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 2px;
  transition: background 0.2s;
}
.conversation-item:hover {
  background: #f5f5f5;
}
.conversation-item.active {
  background: #e6f4ff;
}
.conv-icon {
  color: #8c8c8c;
  flex-shrink: 0;
}
.conversation-item.active .conv-icon {
  color: #1677ff;
}
.conv-title {
  flex: 1;
  font-size: 13px;
  color: #1d2129;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.delete-btn {
  opacity: 0;
  transition: opacity 0.15s;
  color: #8c8c8c;
}
.conversation-item:hover .delete-btn {
  opacity: 1;
}
.sidebar-footer {
  padding: 12px;
  border-top: 1px solid #f0f0f0;
}

/* ===== Message Area ===== */
.message-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 24px 20px;
}

/* ===== Empty State ===== */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 40px 20px;
}
.empty-icon-wrap {
  width: 72px;
  height: 72px;
  border-radius: 50%;
  background: #e6f4ff;
  color: #1677ff;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 20px;
}
.empty-title {
  font-size: 20px;
  font-weight: 600;
  color: #1d2129;
  margin: 0 0 8px;
}
.empty-desc {
  font-size: 14px;
  color: #8c8c8c;
  margin: 0 0 28px;
}
.quick-questions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: center;
  max-width: 560px;
}
.quick-item {
  padding: 8px 16px;
  background: #fff;
  border: 1px solid #e8e8e8;
  border-radius: 18px;
  font-size: 13px;
  color: #595959;
  cursor: pointer;
  transition: all 0.2s;
}
.quick-item:hover {
  border-color: #1677ff;
  color: #1677ff;
  background: #e6f4ff;
}

/* ===== Messages ===== */
.messages-list {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.message-row {
  display: flex;
  gap: 12px;
  max-width: 80%;
}
.message-row.user {
  flex-direction: row-reverse;
  margin-left: auto;
}

/* Avatar */
.avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: #fff;
}
.avatar.user {
  background: #1677ff;
}
.avatar.assistant {
  background: #52c41a;
}
.avatar.human {
  background: #fa8c16;
}

/* Bubble */
.bubble-wrap {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.bubble-header {
  display: flex;
  align-items: center;
  gap: 8px;
}
.message-row.user .bubble-header {
  flex-direction: row-reverse;
}
.role-name {
  font-size: 12px;
  font-weight: 500;
  color: #8c8c8c;
}
.msg-time {
  font-size: 11px;
  color: #bfbfbf;
}
.msg-delete-btn {
  margin-left: 4px;
  opacity: 0;
  color: #8c8c8c;
  transition: opacity 0.15s;
}
.bubble-wrap:hover .msg-delete-btn {
  opacity: 1;
}
.bubble {
  padding: 12px 16px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.7;
  word-break: break-word;
  width: fit-content;
  max-width: 100%;
}
.bubble.user {
  background: #1677ff;
  color: #fff;
  border-bottom-right-radius: 4px;
}
.bubble.assistant {
  background: #fff;
  color: #1d2129;
  border: 1px solid #e8e8e8;
  border-bottom-left-radius: 4px;
}
.bubble.human {
  background: #fff7e6;
  color: #1d2129;
  border: 1px solid #ffe7ba;
  border-bottom-left-radius: 4px;
}
.bubble :deep(code) {
  background: rgba(0,0,0,0.06);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
}
.bubble.user :deep(code) {
  background: rgba(255,255,255,0.2);
}
.bubble :deep(strong) {
  font-weight: 600;
}


/* Typing indicator */
.typing-bubble {
  padding: 14px 18px;
}
.typing-indicator {
  display: flex;
  align-items: center;
  gap: 4px;
  height: 20px;
}
.typing-indicator .dot {
  width: 8px;
  height: 8px;
  background: #a0aec0;
  border-radius: 50%;
  animation: typingPulse 1.4s ease-in-out infinite;
}
.typing-indicator .dot:nth-child(2) {
  animation-delay: 0.15s;
}
.typing-indicator .dot:nth-child(3) {
  animation-delay: 0.3s;
}
@keyframes typingPulse {
  0%, 100% {
    opacity: 0.3;
    transform: scale(0.85);
  }
  50% {
    opacity: 1;
    transform: scale(1);
  }
}

/* ===== Suggest Bar ===== */
.suggest-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  background: #fffbe6;
  border-top: 1px solid #ffe58f;
  font-size: 13px;
  color: #ad6800;
}
.suggest-bar .el-button {
  margin-left: auto;
}

/* ===== Input Area ===== */
.input-area {
  padding: 16px 20px;
  background: #fff;
  border-top: 1px solid #e8e8e8;
}
.input-box {
  margin-bottom: 10px;
}
.input-box :deep(.el-textarea__inner) {
  border-radius: 10px;
  padding: 10px 14px;
  font-size: 14px;
  box-shadow: none;
  border: 1px solid #d9d9d9;
  transition: border-color 0.2s;
}
.input-box :deep(.el-textarea__inner:focus) {
  border-color: #1677ff;
}
.input-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

/* ===== Responsive ===== */
@media (max-width: 768px) {
  .conversation-sidebar {
    display: none;
  }
  .chat-header {
    padding: 0 16px;
  }
  .messages-container {
    padding: 16px 12px;
  }
  .message-row {
    max-width: 90%;
  }
  .input-area {
    padding: 12px;
  }
}
</style>
