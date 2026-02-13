<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Setting, Connection } from '@element-plus/icons-vue'
import {
  getSettings,
  updateSettings,
  getLLMProviders,
  testConnection
} from '@/api/settings'

// Types
interface LLMProvider {
  name: string
  displayName: string
  defaultApiUrl: string
  defaultModel: string
  supportedModels: string[]
}

interface RAGConfig {
  topK: number
  similarityThreshold: number
  useRewrite: boolean
  maxContextLength: number
}

// State
const loading = ref(false)
const saving = ref(false)
const testing = ref(false)

// LLM providers
const providers = ref<LLMProvider[]>([])

// Current settings
const llmConfig = reactive<{
  provider: string
  apiKey: string
  apiUrl: string
  model: string
  hasApiKey: boolean
}>({
  provider: '',
  apiKey: '',
  apiUrl: '',
  model: '',
  hasApiKey: false
})

const embeddingConfig = reactive<{
  provider: string
  apiKey: string
  apiUrl: string
  model: string
  dimension: number
  hasApiKey: boolean
}>({
  provider: '',
  apiKey: '',
  apiUrl: '',
  model: 'BAAI/bge-large-zh-v1.5',
  dimension: 1024,
  hasApiKey: false
})

const ragConfig = reactive<RAGConfig>({
  topK: 5,
  similarityThreshold: 0.5,
  useRewrite: true,
  maxContextLength: 2000
})

const generalConfig = reactive({
  timezone: 'Asia/Shanghai'
})

const timezoneOptions = [
  'Asia/Shanghai',
  'Asia/Tokyo',
  'Asia/Singapore',
  'Asia/Hong_Kong',
  'America/New_York',
  'America/Los_Angeles',
  'Europe/London',
  'UTC',
]

// Selected provider info
const selectedProvider = computed(() => {
  return providers.value.find(p => p.name === llmConfig.provider)
})

// Available models for selected provider
const availableModels = computed(() => {
  return selectedProvider.value?.supportedModels || []
})

// Load settings
async function loadSettings() {
  loading.value = true
  try {
    const [settingsRes, providersRes] = await Promise.all([
      getSettings(),
      getLLMProviders()
    ])
    
    // Transform providers
    const providersData = providersRes.data as any
    providers.value = (providersData.providers || providersData || []).map((p: any) => ({
      name: p.name,
      displayName: p.display_name || p.displayName,
      defaultApiUrl: p.default_api_url || p.defaultApiUrl,
      defaultModel: p.default_model || p.defaultModel,
      supportedModels: p.supported_models || p.supportedModels || []
    }))
    
    // Transform LLM config
    const settingsData = settingsRes.data as any
    const llm = settingsData.llm || settingsData
    llmConfig.provider = llm.provider || llm.llmProvider || ''
    llmConfig.apiKey = ''  // Don't show actual key
    llmConfig.apiUrl = llm.api_url || llm.llmApiUrl || ''
    llmConfig.model = llm.model || llm.llmModel || ''
    llmConfig.hasApiKey = llm.has_api_key || !!llm.llmApiKey
    
    // Transform Embedding config
    const embedding = settingsData.embedding || {}
    embeddingConfig.provider = embedding.provider || llmConfig.provider
    embeddingConfig.apiKey = ''  // Don't show actual key
    embeddingConfig.apiUrl = embedding.api_url || ''
    embeddingConfig.model = embedding.model || 'BAAI/bge-large-zh-v1.5'
    embeddingConfig.dimension = embedding.dimension || 1024
    embeddingConfig.hasApiKey = embedding.has_api_key || false
    
    // Transform RAG config
    const rag = settingsData.rag || settingsData
    ragConfig.topK = rag.top_k || rag.ragTopK || 5
    ragConfig.similarityThreshold = rag.similarity_threshold || rag.ragSimilarityThreshold || 0.5
    ragConfig.useRewrite = rag.use_rewrite !== undefined ? rag.use_rewrite : true
    ragConfig.maxContextLength = rag.max_context_length || 2000

    // Transform General config
    const general = settingsData.general || {}
    generalConfig.timezone = general.timezone || 'Asia/Shanghai'
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '加载设置失败')
  } finally {
    loading.value = false
  }
}

// Handle provider change
function handleProviderChange() {
  const provider = selectedProvider.value
  if (provider) {
    llmConfig.apiUrl = provider.defaultApiUrl
    llmConfig.model = provider.defaultModel
  }
}

// Save LLM settings
async function saveLLMSettings() {
  saving.value = true
  try {
    const data: any = {
      llm: {
        provider: llmConfig.provider,
        api_url: llmConfig.apiUrl,
        model: llmConfig.model
      }
    }
    
    // Only include API key if it was changed
    if (llmConfig.apiKey) {
      data.llm.api_key = llmConfig.apiKey
    }
    
    await updateSettings(data)
    ElMessage.success('LLM设置已保存')
    llmConfig.apiKey = ''  // Clear the input
    llmConfig.hasApiKey = true
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

// Save Embedding settings
async function saveEmbeddingSettings() {
  saving.value = true
  try {
    const data: any = {
      embedding: {
        provider: embeddingConfig.provider,
        api_url: embeddingConfig.apiUrl,
        model: embeddingConfig.model,
        dimension: embeddingConfig.dimension
      }
    }
    
    // Only include API key if it was changed
    if (embeddingConfig.apiKey) {
      data.embedding.api_key = embeddingConfig.apiKey
    }
    
    await updateSettings(data)
    ElMessage.success('Embedding设置已保存')
    embeddingConfig.apiKey = ''  // Clear the input
    embeddingConfig.hasApiKey = true
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

// Save RAG settings
async function saveRAGSettings() {
  saving.value = true
  try {
    await updateSettings({
      rag: {
        top_k: ragConfig.topK,
        similarity_threshold: ragConfig.similarityThreshold,
        use_rewrite: ragConfig.useRewrite,
        max_context_length: ragConfig.maxContextLength
      }
    })
    ElMessage.success('RAG设置已保存')
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

// Save General settings
async function saveGeneralSettings() {
  saving.value = true
  try {
    await updateSettings({
      general: {
        timezone: generalConfig.timezone
      }
    })
    ElMessage.success('通用设置已保存')
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

// Test connection
async function handleTestConnection() {
  if (!llmConfig.provider) {
    ElMessage.warning('请先选择LLM提供商')
    return
  }
  
  // 需要API密钥才能测试
  const apiKey = llmConfig.apiKey || ''
  if (!apiKey && !llmConfig.hasApiKey) {
    ElMessage.warning('请先输入API密钥')
    return
  }
  
  testing.value = true
  try {
    const response = await testConnection({
      provider: llmConfig.provider,
      api_key: apiKey,
      api_url: llmConfig.apiUrl || undefined,
      model: llmConfig.model || undefined
    })
    if (response.data.success) {
      ElMessage.success(response.data.message || '连接成功')
    } else {
      ElMessage.error(response.data.message || '连接失败')
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '测试连接失败')
  } finally {
    testing.value = false
  }
}

// Initialize
onMounted(() => {
  loadSettings()
})
</script>

<template>
  <div class="settings-container">
    <!-- Header -->
    <div class="page-header">
      <h1>系统设置</h1>
      <p class="page-description">
        配置LLM提供商和RAG参数
      </p>
    </div>

    <div
      v-loading="loading"
      class="settings-content"
    >
      <!-- LLM Settings -->
      <el-card
        class="settings-card"
        shadow="never"
      >
        <template #header>
          <div class="card-header">
            <span><el-icon><Setting /></el-icon> LLM提供商配置</span>
          </div>
        </template>
        
        <el-form
          label-width="140px"
          label-position="left"
        >
          <el-form-item label="提供商">
            <el-select
              v-model="llmConfig.provider"
              placeholder="选择LLM提供商"
              style="width: 300px"
              @change="handleProviderChange"
            >
              <el-option
                v-for="provider in providers"
                :key="provider.name"
                :label="provider.displayName"
                :value="provider.name"
              />
            </el-select>
          </el-form-item>
          
          <el-form-item label="API密钥">
            <el-input
              v-model="llmConfig.apiKey"
              type="password"
              :placeholder="llmConfig.hasApiKey ? '已配置（留空保持不变）' : '请输入API密钥'"
              style="width: 300px"
              show-password
            />
            <el-tag
              v-if="llmConfig.hasApiKey"
              type="success"
              size="small"
              style="margin-left: 12px"
            >
              已配置
            </el-tag>
          </el-form-item>
          
          <el-form-item label="API地址">
            <el-input
              v-model="llmConfig.apiUrl"
              placeholder="API地址"
              style="width: 400px"
            />
          </el-form-item>
          
          <el-form-item label="模型">
            <el-select
              v-model="llmConfig.model"
              placeholder="选择模型"
              style="width: 300px"
              filterable
              allow-create
            >
              <el-option
                v-for="model in availableModels"
                :key="model"
                :label="model"
                :value="model"
              />
            </el-select>
          </el-form-item>
          
          <el-form-item>
            <el-button
              type="primary"
              :loading="saving"
              @click="saveLLMSettings"
            >
              保存LLM设置
            </el-button>
            <el-button 
              :icon="Connection" 
              :loading="testing" 
              @click="handleTestConnection"
            >
              测试连接
            </el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- Embedding Settings -->
      <el-card
        class="settings-card"
        shadow="never"
      >
        <template #header>
          <div class="card-header">
            <span><el-icon><Setting /></el-icon> Embedding模型配置</span>
          </div>
        </template>
        
        <el-form
          label-width="140px"
          label-position="left"
        >
          <el-form-item label="提供商">
            <el-select
              v-model="embeddingConfig.provider"
              placeholder="选择提供商（通常与LLM相同）"
              style="width: 300px"
            >
              <el-option
                v-for="provider in providers"
                :key="provider.name"
                :label="provider.displayName"
                :value="provider.name"
              />
            </el-select>
            <div class="form-tip">
              通常使用与LLM相同的提供商
            </div>
          </el-form-item>
          
          <el-form-item label="API密钥">
            <el-input
              v-model="embeddingConfig.apiKey"
              type="password"
              :placeholder="embeddingConfig.hasApiKey ? '已配置（留空保持不变）' : '留空则使用LLM的API密钥'"
              style="width: 300px"
              show-password
            />
            <el-tag
              v-if="embeddingConfig.hasApiKey"
              type="success"
              size="small"
              style="margin-left: 12px"
            >
              已配置
            </el-tag>
            <el-tag
              v-else
              type="info"
              size="small"
              style="margin-left: 12px"
            >
              使用LLM密钥
            </el-tag>
          </el-form-item>
          
          <el-form-item label="API地址">
            <el-input
              v-model="embeddingConfig.apiUrl"
              placeholder="留空则使用提供商默认地址"
              style="width: 400px"
            />
          </el-form-item>
          
          <el-form-item label="模型">
            <el-select
              v-model="embeddingConfig.model"
              placeholder="选择Embedding模型"
              style="width: 300px"
              filterable
              allow-create
            >
              <el-option
                label="BAAI/bge-large-zh-v1.5"
                value="BAAI/bge-large-zh-v1.5"
              />
              <el-option
                label="BAAI/bge-m3"
                value="BAAI/bge-m3"
              />
              <el-option
                label="text-embedding-ada-002"
                value="text-embedding-ada-002"
              />
              <el-option
                label="text-embedding-3-small"
                value="text-embedding-3-small"
              />
              <el-option
                label="text-embedding-3-large"
                value="text-embedding-3-large"
              />
            </el-select>
          </el-form-item>
          
          <el-form-item label="向量维度">
            <el-input-number
              v-model="embeddingConfig.dimension"
              :min="64"
              :max="4096"
              :step="64"
              style="width: 200px"
            />
            <div class="form-tip">
              根据所选模型设置，bge-large-zh为1024，ada-002为1536
            </div>
          </el-form-item>
          
          <el-form-item>
            <el-button
              type="primary"
              :loading="saving"
              @click="saveEmbeddingSettings"
            >
              保存Embedding设置
            </el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- RAG Settings -->
      <el-card
        class="settings-card"
        shadow="never"
      >
        <template #header>
          <div class="card-header">
            <span><el-icon><Setting /></el-icon> RAG参数配置</span>
          </div>
        </template>
        
        <el-form
          label-width="140px"
          label-position="left"
        >
          <el-form-item label="检索数量 (Top-K)">
            <el-slider
              v-model="ragConfig.topK"
              :min="1"
              :max="20"
              :step="1"
              show-input
              style="width: 400px"
            />
            <div class="form-tip">
              检索最相关的知识条目数量
            </div>
          </el-form-item>
          
          <el-form-item label="相似度阈值">
            <el-slider
              v-model="ragConfig.similarityThreshold"
              :min="0"
              :max="1"
              :step="0.05"
              show-input
              style="width: 400px"
            />
            <div class="form-tip">
              低于此阈值的结果将被过滤
            </div>
          </el-form-item>
          
          <el-form-item label="查询改写">
            <el-switch v-model="ragConfig.useRewrite" />
            <span class="switch-label">{{ ragConfig.useRewrite ? '启用' : '禁用' }}</span>
            <div class="form-tip">
              启用查询改写（停用词过滤 + 同义词扩展）以提高检索效果
            </div>
          </el-form-item>
          
          <el-form-item label="最大上下文长度">
            <el-input-number
              v-model="ragConfig.maxContextLength"
              :min="500"
              :max="10000"
              :step="500"
              style="width: 200px"
            />
            <span class="unit">字符</span>
            <div class="form-tip">
              传递给LLM的最大上下文长度
            </div>
          </el-form-item>
          
          <el-form-item>
            <el-button
              type="primary"
              :loading="saving"
              @click="saveRAGSettings"
            >
              保存RAG设置
            </el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- General Settings -->
      <el-card
        class="settings-card"
        shadow="never"
      >
        <template #header>
          <div class="card-header">
            <span><el-icon><Setting /></el-icon> 通用配置</span>
          </div>
        </template>
        
        <el-form
          label-width="140px"
          label-position="left"
        >
          <el-form-item label="系统时区">
            <el-select
              v-model="generalConfig.timezone"
              placeholder="选择时区"
              style="width: 300px"
              filterable
              allow-create
            >
              <el-option
                v-for="tz in timezoneOptions"
                :key="tz"
                :label="tz"
                :value="tz"
              />
            </el-select>
            <div class="form-tip">
              所有时间显示将使用此时区，默认 Asia/Shanghai (UTC+8)
            </div>
          </el-form-item>
          
          <el-form-item>
            <el-button
              type="primary"
              :loading="saving"
              @click="saveGeneralSettings"
            >
              保存通用设置
            </el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- Provider Info -->
      <el-card
        v-if="selectedProvider"
        class="info-card"
        shadow="never"
      >
        <template #header>
          <span>{{ selectedProvider.displayName }} 信息</span>
        </template>
        <el-descriptions
          :column="1"
          border
        >
          <el-descriptions-item label="默认API地址">
            {{ selectedProvider.defaultApiUrl }}
          </el-descriptions-item>
          <el-descriptions-item label="默认模型">
            {{ selectedProvider.defaultModel }}
          </el-descriptions-item>
          <el-descriptions-item label="支持的模型">
            <el-tag
              v-for="model in selectedProvider.supportedModels"
              :key="model"
              size="small"
              style="margin: 2px"
            >
              {{ model }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.settings-container {
  padding: 20px;
  max-width: 900px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 24px;
}

.page-header h1 {
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

.settings-card,
.info-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  align-items: center;
}

.card-header span {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
}

.form-tip {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}

.switch-label {
  margin-left: 12px;
  font-size: 14px;
  color: var(--el-text-color-regular);
}

.unit {
  margin-left: 8px;
  font-size: 14px;
  color: var(--el-text-color-secondary);
}

/* Responsive */
@media (max-width: 768px) {
  .settings-container {
    padding: 16px;
  }
  
  :deep(.el-form-item__content) {
    flex-wrap: wrap;
  }
}
</style>
