import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import type { Conversation, Message, PaginatedResponse } from '@/types'
import * as chatApi from '@/api/chat'

export const useChatStore = defineStore('chat', () => {
  // State
  const conversations = ref<Conversation[]>([])
  const currentConversation = ref<Conversation | null>(null)
  const messages = ref<Message[]>([])
  const isLoading = ref(false)
  const isSending = ref(false)
  const isStreaming = ref(false)
  const streamingContent = ref('')
  const suggestHuman = ref(false)
  
  // Pagination state
  const conversationPage = ref(1)
  const conversationTotal = ref(0)
  const conversationPageSize = ref(20)
  const messagePage = ref(1)
  const messageTotal = ref(0)
  const messagePageSize = ref(20)
  const hasMoreMessages = ref(false)

  // ── 临时消息 ID（负数递减，避免污染 since_id） ──
  let _tempIdCounter = 0
  function nextTempId(): number {
    return --_tempIdCounter
  }

  /** 仅基于已确认服务端 ID（正数）的最大值，用于 since_id 增量拉取 */
  const maxConfirmedId = computed(() => {
    const confirmed = messages.value.filter(m => m.id > 0).map(m => m.id)
    return confirmed.length > 0 ? Math.max(...confirmed) : 0
  })

  /** 将临时消息 ID 就地替换为服务端真实 ID */
  function replaceMessageId(tempId: number, realId: number) {
    const idx = messages.value.findIndex(m => m.id === tempId)
    if (idx !== -1) {
      messages.value[idx].id = realId
      messages.value[idx]._isTemp = false
      // 标记为已见
      const convId = messages.value[idx].conversationId
      if (convId) _markSeen(convId, realId)
    }
  }

  // WebSocket 发送回调（由视图层注册，用于人工模式优先走 WS）
  let _wsSendFn: ((data: any) => boolean) | null = null

  function setWsSender(fn: ((data: any) => boolean) | null) {
    _wsSendFn = fn
  }

  // Computed
  const hasConversations = computed(() => conversations.value.length > 0)
  const hasMessages = computed(() => messages.value.length > 0)
  const sortedMessages = computed(() => 
    [...messages.value].sort((a, b) => 
      new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    )
  )

  // Conversation list management
  function setConversations(list: Conversation[]) {
    conversations.value = list
  }

  function addConversation(conversation: Conversation) {
    conversations.value.unshift(conversation)
  }

  function updateConversation(id: string, updates: Partial<Conversation>) {
    const index = conversations.value.findIndex(c => c.id === id)
    if (index !== -1) {
      conversations.value[index] = { ...conversations.value[index], ...updates }
    }
    if (currentConversation.value?.id === id) {
      currentConversation.value = { ...currentConversation.value, ...updates }
    }
  }

  function removeConversation(id: string) {
    conversations.value = conversations.value.filter(c => c.id !== id)
    if (currentConversation.value?.id === id) {
      currentConversation.value = null
      messages.value = []
    }
  }

  function setCurrentConversation(conversation: Conversation | null) {
    currentConversation.value = conversation
    if (!conversation) {
      messages.value = []
      messagePage.value = 1
      messageTotal.value = 0
    }
  }

  // Message management
  /** 已见消息 ID 缓存窗口（用于跨端幂等去重） */
  const _seenMessageIds = new Set<string>()
  const SEEN_CACHE_MAX = 500

  function _makeIdempotentKey(conversationId: string, messageId: number): string {
    return `${conversationId}:${messageId}`
  }

  function _markSeen(conversationId: string, messageId: number) {
    const key = _makeIdempotentKey(conversationId, messageId)
    _seenMessageIds.add(key)
    // 防止缓存无限增长
    if (_seenMessageIds.size > SEEN_CACHE_MAX) {
      const iter = _seenMessageIds.values()
      for (let i = 0; i < 100; i++) iter.next()
      // 删除最早的 100 个
      const toDelete: string[] = []
      const it = _seenMessageIds.values()
      for (let i = 0; i < 100; i++) {
        const r = it.next()
        if (r.done) break
        toDelete.push(r.value)
      }
      toDelete.forEach(k => _seenMessageIds.delete(k))
    }
  }

  function isMessageSeen(conversationId: string, messageId: number): boolean {
    return _seenMessageIds.has(_makeIdempotentKey(conversationId, messageId))
  }

  function setMessages(list: Message[]) {
    messages.value = list
    // 将所有消息标记为已见
    for (const m of list) {
      if (m.id && m.conversationId) _markSeen(m.conversationId, m.id)
    }
  }

  function prependMessages(list: Message[]) {
    messages.value = [...list, ...messages.value]
  }

  function addMessage(message: Message) {
    // 幂等去重：conversation_id + message_id
    if (message.id && message.conversationId && isMessageSeen(message.conversationId, message.id)) {
      return // 已存在，跳过
    }
    // 额外检查 messages 数组（防止临时 ID 冲突）
    if (messages.value.some(m => m.id === message.id)) {
      return
    }
    messages.value.push(message)
    if (message.id && message.conversationId) _markSeen(message.conversationId, message.id)
  }

  function updateLastMessage(content: string) {
    if (messages.value.length > 0) {
      messages.value[messages.value.length - 1].content = content
    }
  }

  function updateMessageById(id: number, updates: Partial<Message>) {
    const index = messages.value.findIndex(m => m.id === id)
    if (index !== -1) {
      messages.value[index] = { ...messages.value[index], ...updates }
    }
  }

  // Loading states
  function setLoading(loading: boolean) {
    isLoading.value = loading
  }

  function setSending(sending: boolean) {
    isSending.value = sending
  }

  function setStreaming(streaming: boolean) {
    isStreaming.value = streaming
  }

  function setStreamingContent(content: string) {
    streamingContent.value = content
  }

  function appendStreamingContent(chunk: string) {
    streamingContent.value += chunk
  }

  function clearStreamingContent() {
    streamingContent.value = ''
  }

  // API Actions
  async function fetchConversations(page = 1, pageSize = 20) {
    setLoading(true)
    try {
      const response = await chatApi.getConversations({ page, page_size: pageSize })
      const data = response.data as PaginatedResponse<Conversation>
      setConversations(data.items)
      conversationPage.value = data.page
      conversationTotal.value = data.total
      conversationPageSize.value = data.page_size || pageSize
      return data
    } catch (error) {
      console.error('Failed to fetch conversations:', error)
      throw error
    } finally {
      setLoading(false)
    }
  }

  async function createNewConversation() {
    setLoading(true)
    try {
      const response = await chatApi.createConversation()
      const conversation = response.data as Conversation
      addConversation(conversation)
      setCurrentConversation(conversation)
      messages.value = []
      return conversation
    } catch (error) {
      console.error('Failed to create conversation:', error)
      ElMessage.error('创建对话失败')
      throw error
    } finally {
      setLoading(false)
    }
  }

  async function deleteConversationById(id: string) {
    try {
      await chatApi.deleteConversation(id)
      removeConversation(id)
      ElMessage.success('对话已删除')
    } catch (error) {
      console.error('Failed to delete conversation:', error)
      ElMessage.error('删除对话失败')
      throw error
    }
  }

  async function deleteMessageById(messageId: number, hard = false) {
    if (!currentConversation.value) return
    try {
      await chatApi.deleteMessage(currentConversation.value.id, messageId, hard)
      messages.value = messages.value.filter(m => m.id !== messageId)
      messageTotal.value = Math.max(0, messageTotal.value - 1)
      ElMessage.success(hard ? '消息已彻底删除' : '消息已删除')
    } catch (error) {
      console.error('Failed to delete message:', error)
      ElMessage.error('删除消息失败')
      throw error
    }
  }

  async function fetchMessages(conversationId: string, page = 1, pageSize = 20) {
    setLoading(true)
    try {
      const response = await chatApi.getMessages(conversationId, { page, page_size: pageSize })
      const data = response.data as PaginatedResponse<Message>
      
      if (page === 1) {
        setMessages(data.items)
      } else {
        prependMessages(data.items)
      }
      
      messagePage.value = data.page
      messageTotal.value = data.total
      messagePageSize.value = data.page_size || pageSize
      hasMoreMessages.value = data.items.length === pageSize && messages.value.length < data.total
      
      return data
    } catch (error) {
      console.error('Failed to fetch messages:', error)
      throw error
    } finally {
      setLoading(false)
    }
  }

  async function loadMoreMessages() {
    if (!currentConversation.value || !hasMoreMessages.value || isLoading.value) {
      return
    }
    const nextPage = messagePage.value + 1
    await fetchMessages(currentConversation.value.id, nextPage, messagePageSize.value)
  }

  async function sendMessageWithStream(content: string) {
    if (!currentConversation.value || isSending.value) {
      return
    }

    const convStatus = currentConversation.value.status

    setSending(true)
    clearStreamingContent()
    suggestHuman.value = false

    // Add user message immediately (negative temp ID, won't pollute since_id)
    const userTempId = nextTempId()
    const userMessage: Message = {
      id: userTempId,
      conversationId: currentConversation.value.id,
      role: 'user',
      content,
      timestamp: new Date().toISOString(),
      _isTemp: true,
    }
    addMessage(userMessage)

    // 人工处理中：优先通过 WebSocket 发送，降级走 REST
    if (convStatus === 'human_handling') {
      try {
        const sent = _wsSendFn?.({
          type: 'message',
          conversation_id: currentConversation.value.id,
          content,
        })
        if (!sent) {
          // WS 不可用，降级 REST
          const token = localStorage.getItem('token') || localStorage.getItem('guest_token') || ''
          const response = await fetch(`/api/chat/conversations/${currentConversation.value.id}/messages`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${token}`,
            },
            body: JSON.stringify({ content })
          })
          if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`)
          }
        }
      } catch (error) {
        console.error('Failed to send message in human_handling:', error)
        ElMessage.error('发送消息失败')
      } finally {
        setSending(false)
      }
      return
    }

    setStreaming(true)

    // Add placeholder for assistant message (only for AI mode)
    const assistantTempId = nextTempId()
    const assistantMessage: Message = {
      id: assistantTempId,
      conversationId: currentConversation.value.id,
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString(),
      _isTemp: true,
    }
    addMessage(assistantMessage)

    try {
      // Use SSE for streaming response
      const token = localStorage.getItem('token') || localStorage.getItem('guest_token') || ''
      const response = await fetch(`/api/chat/conversations/${currentConversation.value.id}/messages`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
          'Accept': 'text/event-stream'
        },
        body: JSON.stringify({ content })
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const reader = response.body?.getReader()
      const decoder = new TextDecoder()

      if (reader) {
        let fullContent = ''
        let buffer = ''
        
        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          
          // Keep the last incomplete line in buffer
          buffer = lines.pop() || ''

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const data = line.slice(6).trim()
              if (data === '[DONE]') {
                continue
              }
              try {
                const parsed = JSON.parse(data)
                
                // Handle different event types
                if (parsed.type === 'content' && parsed.content) {
                  fullContent += parsed.content
                  setStreamingContent(fullContent)
                  updateLastMessage(fullContent)
                } else if (parsed.type === 'error') {
                  // Handle error from backend
                  fullContent = parsed.message || '发生错误'
                  updateLastMessage(fullContent)
                  ElMessage.error(parsed.message || '发送消息失败')
                } else if (parsed.type === 'start') {
                  // 服务端确认用户消息已保存，替换临时 ID
                  if (parsed.user_message_id) {
                    replaceMessageId(userTempId, parsed.user_message_id)
                  }
                } else if (parsed.type === 'end') {
                  // 服务端确认助手消息已保存，替换临时 ID
                  if (parsed.message_id) {
                    replaceMessageId(assistantTempId, parsed.message_id)
                  }
                  if (parsed.confidence !== undefined) {
                    updateMessageById(parsed.message_id || assistantMessage.id, { confidence: parsed.confidence })
                  }
                } else if (parsed.type === 'rag_trace' && parsed.trace) {
                  updateMessageById(assistantMessage.id, { ragTrace: parsed.trace })
                } else if (parsed.type === 'low_confidence') {
                  // 低置信度事件：标记建议转人工
                  suggestHuman.value = true
                } else if (parsed.content) {
                  // Fallback for direct content
                  fullContent += parsed.content
                  setStreamingContent(fullContent)
                  updateLastMessage(fullContent)
                }
                
                if (parsed.confidence !== undefined && parsed.type !== 'end') {
                  updateMessageById(assistantMessage.id, { confidence: parsed.confidence })
                }
                if (parsed.ragTrace) {
                  updateMessageById(assistantMessage.id, { ragTrace: parsed.ragTrace })
                }
              } catch {
                // Non-JSON data, might be raw content
                if (data.trim()) {
                  fullContent += data
                  setStreamingContent(fullContent)
                  updateLastMessage(fullContent)
                }
              }
            }
          }
        }
      }

      // Update conversation title if it's the first message
      if (messages.value.length <= 2) {
        updateConversation(currentConversation.value.id, {
          title: content.slice(0, 50) + (content.length > 50 ? '...' : ''),
          updatedAt: new Date().toISOString()
        })
      }

    } catch (error) {
      console.error('Failed to send message:', error)
      // Remove the placeholder assistant message on error
      messages.value = messages.value.filter(m => m.id !== assistantMessage.id)
      ElMessage.error('发送消息失败')
      throw error
    } finally {
      setSending(false)
      setStreaming(false)
      clearStreamingContent()
    }
  }

  async function transferToHumanService() {
    if (!currentConversation.value) {
      return
    }

    try {
      await chatApi.transferToHuman(currentConversation.value.id)
      updateConversation(currentConversation.value.id, { status: 'pending_human' })
      ElMessage.success('已转接人工客服，请稍候')
    } catch (error) {
      console.error('Failed to transfer to human:', error)
      ElMessage.error('转接人工客服失败')
      throw error
    }
  }

  // Reset store
  function $reset() {
    conversations.value = []
    currentConversation.value = null
    messages.value = []
    isLoading.value = false
    isSending.value = false
    isStreaming.value = false
    streamingContent.value = ''
    suggestHuman.value = false
    conversationPage.value = 1
    conversationTotal.value = 0
    messagePage.value = 1
    messageTotal.value = 0
    hasMoreMessages.value = false
    _seenMessageIds.clear()
  }

  return {
    // State
    conversations,
    currentConversation,
    messages,
    isLoading,
    isSending,
    isStreaming,
    streamingContent,
    suggestHuman,
    conversationPage,
    conversationTotal,
    conversationPageSize,
    messagePage,
    messageTotal,
    messagePageSize,
    hasMoreMessages,
    
    // Computed
    hasConversations,
    hasMessages,
    sortedMessages,
    
    // Mutations
    setConversations,
    addConversation,
    updateConversation,
    removeConversation,
    setCurrentConversation,
    setMessages,
    prependMessages,
    addMessage,
    updateLastMessage,
    updateMessageById,
    isMessageSeen,
    setLoading,
    setSending,
    setStreaming,
    setStreamingContent,
    appendStreamingContent,
    clearStreamingContent,
    
    // Actions
    fetchConversations,
    createNewConversation,
    deleteConversationById,
    deleteMessageById,
    fetchMessages,
    loadMoreMessages,
    sendMessageWithStream,
    transferToHumanService,
    setWsSender,
    nextTempId,
    maxConfirmedId,
    replaceMessageId,
    $reset
  }
})
