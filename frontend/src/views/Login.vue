<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock, ChatDotRound, UserFilled } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { registerCustomer } from '@/api/auth'
import {
  clearGuestIdentityData,
  getGuestConversationIds,
  getOrCreateGuestDeviceId,
} from '@/utils/guestIdentity'
import type { FormInstance, FormRules } from 'element-plus'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const GUEST_TOKEN_KEY = 'guest_token'
const VISITOR_ID_KEY = 'visitor_id'

// Active tab: login or register
const activeTab = ref('login')

// Login form
const loginFormRef = ref<FormInstance>()
const loginForm = reactive({
  username: '',
  password: ''
})

// Register form
const registerFormRef = ref<FormInstance>()
const registerForm = reactive({
  username: '',
  password: '',
  confirmPassword: '',
  display_name: ''
})

const registerLoading = ref(false)

// Login validation rules
const loginRules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 2, max: 50, message: '用户名长度应为2-50个字符', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 100, message: '密码长度应为6-100个字符', trigger: 'blur' }
  ]
}

// Register validation rules
const registerRules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 50, message: '用户名长度应为3-50个字符', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 100, message: '密码长度应为6-100个字符', trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    {
      validator: (_rule: unknown, value: string, callback: (err?: Error) => void) => {
        if (value !== registerForm.password) {
          callback(new Error('两次输入的密码不一致'))
        } else {
          callback()
        }
      },
      trigger: 'blur'
    }
  ],
  display_name: [
    { required: true, message: '请输入昵称', trigger: 'blur' },
    { min: 1, max: 100, message: '昵称长度应为1-100个字符', trigger: 'blur' }
  ]
}

/** Get stored visitor_id for conversation migration */
function getVisitorId(): string | undefined {
  return localStorage.getItem(VISITOR_ID_KEY) || undefined
}

/** Clear guest token after successful login/register */
function clearGuestData() {
  localStorage.removeItem(GUEST_TOKEN_KEY)
  localStorage.removeItem(VISITOR_ID_KEY)
  clearGuestIdentityData()
}

// Handle login
async function handleLogin() {
  if (!loginFormRef.value) return
  try {
    await loginFormRef.value.validate()
  } catch {
    return
  }

  const visitorId = getVisitorId()
  const success = await authStore.login({
    username: loginForm.username,
    password: loginForm.password,
    visitor_id: visitorId,
    guest_device_id: getOrCreateGuestDeviceId(),
    guest_conversation_ids: getGuestConversationIds(),
  })

  if (success) {
    clearGuestData()
    ElMessage.success('登录成功')
    const redirect = route.query.redirect as string
    const role = authStore.user?.role
    if (role === 'customer') {
      router.push('/')
    } else {
      router.push(redirect || '/workbench')
    }
  }
}

// Handle customer registration
async function handleRegister() {
  if (!registerFormRef.value) return
  try {
    await registerFormRef.value.validate()
  } catch {
    return
  }

  registerLoading.value = true
  try {
    const visitorId = getVisitorId()
    const res = await registerCustomer({
      username: registerForm.username,
      password: registerForm.password,
      display_name: registerForm.display_name,
      visitor_id: visitorId,
      guest_device_id: getOrCreateGuestDeviceId(),
      guest_conversation_ids: getGuestConversationIds(),
    })
    const { access_token, refresh_token, user } = res.data
    authStore.setAuth(user, access_token, refresh_token)
    clearGuestData()
    ElMessage.success('注册成功')
    router.push('/')
  } catch (err: unknown) {
    const axiosError = err as { response?: { status?: number; data?: { detail?: string } } }
    if (axiosError.response?.status === 409) {
      ElMessage.error('用户名已存在')
    } else if (axiosError.response?.data?.detail) {
      ElMessage.error(axiosError.response.data.detail)
    } else {
      ElMessage.error('注册失败，请稍后重试')
    }
  } finally {
    registerLoading.value = false
  }
}

// Handle Enter key press
function handleKeyPress(event: KeyboardEvent) {
  if (event.key === 'Enter') {
    if (activeTab.value === 'login') handleLogin()
    else handleRegister()
  }
}

// Check if already authenticated on mount
onMounted(() => {
  if (authStore.isAuthenticated && authStore.user) {
    if (authStore.user.role === 'customer') {
      router.push('/')
    } else {
      router.push('/workbench')
    }
  }
})

// Go to customer chat page
function goToCustomerChat() {
  router.push('/')
}
</script>

<template>
  <div class="login-container">
    <div class="login-card">
      <div class="login-header">
        <h1 class="login-title">智能电商客服系统</h1>
        <p class="login-subtitle">登录或注册您的账户</p>
      </div>

      <el-tabs v-model="activeTab" class="login-tabs">
        <el-tab-pane label="登录" name="login">
          <el-form
            ref="loginFormRef"
            :model="loginForm"
            :rules="loginRules"
            class="login-form"
            @keypress="handleKeyPress"
          >
            <el-form-item prop="username">
              <el-input v-model="loginForm.username" placeholder="用户名" size="large" :prefix-icon="User" clearable />
            </el-form-item>
            <el-form-item prop="password">
              <el-input v-model="loginForm.password" type="password" placeholder="密码" size="large" :prefix-icon="Lock" show-password clearable />
            </el-form-item>
            <el-form-item v-if="authStore.error" class="error-item">
              <el-alert :title="authStore.error" type="error" :closable="false" show-icon />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" size="large" class="login-button" :loading="authStore.loading" @click="handleLogin">
                {{ authStore.loading ? '登录中...' : '登录' }}
              </el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="注册" name="register">
          <el-form
            ref="registerFormRef"
            :model="registerForm"
            :rules="registerRules"
            class="login-form"
            @keypress="handleKeyPress"
          >
            <el-form-item prop="username">
              <el-input v-model="registerForm.username" placeholder="用户名" size="large" :prefix-icon="User" clearable />
            </el-form-item>
            <el-form-item prop="display_name">
              <el-input v-model="registerForm.display_name" placeholder="昵称" size="large" :prefix-icon="UserFilled" clearable />
            </el-form-item>
            <el-form-item prop="password">
              <el-input v-model="registerForm.password" type="password" placeholder="密码" size="large" :prefix-icon="Lock" show-password clearable />
            </el-form-item>
            <el-form-item prop="confirmPassword">
              <el-input v-model="registerForm.confirmPassword" type="password" placeholder="确认密码" size="large" :prefix-icon="Lock" show-password clearable />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" size="large" class="login-button" :loading="registerLoading" @click="handleRegister">
                {{ registerLoading ? '注册中...' : '注册' }}
              </el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>
      </el-tabs>

      <div class="login-footer">
        <el-button type="primary" link class="customer-link" @click="goToCustomerChat">
          <el-icon><ChatDotRound /></el-icon>
          直接使用智能客服
        </el-button>
        <p class="footer-text">© 2026 智能电商客服RAG系统</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-container {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: #f0f2f5;
  padding: 20px;
}
.login-card {
  width: 100%;
  max-width: 420px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.08);
  padding: 40px;
}
.login-header {
  text-align: center;
  margin-bottom: 24px;
}
.login-title {
  font-size: 24px;
  font-weight: 600;
  color: #303133;
  margin: 0 0 8px 0;
}
.login-subtitle {
  font-size: 14px;
  color: #909399;
  margin: 0;
}
.login-tabs :deep(.el-tabs__header) {
  margin-bottom: 20px;
}
.login-tabs :deep(.el-tabs__nav-wrap::after) {
  height: 1px;
}
.login-form :deep(.el-input__wrapper) {
  border-radius: 8px;
}
.login-form :deep(.el-form-item) {
  margin-bottom: 20px;
}
.error-item { margin-bottom: 16px; }
.error-item :deep(.el-alert) { width: 100%; }
.login-button {
  width: 100%;
  border-radius: 8px;
  font-size: 16px;
  height: 44px;
}

.login-footer {
  text-align: center;
  padding-top: 20px;
  border-top: 1px solid #ebeef5;
}
.footer-text {
  font-size: 12px;
  color: #909399;
  margin: 0;
}
.customer-link {
  margin-bottom: 12px;
  font-size: 14px;
}
.customer-link .el-icon {
  margin-right: 4px;
}
</style>
