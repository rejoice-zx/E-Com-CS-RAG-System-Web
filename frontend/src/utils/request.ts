import axios, { AxiosError, InternalAxiosRequestConfig, AxiosResponse } from 'axios'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import router from '@/router'
import { getOrCreateGuestDeviceId } from '@/utils/guestIdentity'

// Create axios instance
const request = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// Request interceptor - attach JWT token
request.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const authStore = useAuthStore()
    if (authStore.token) {
      config.headers.Authorization = `Bearer ${authStore.token}`
    }
    config.headers['X-Device-ID'] = getOrCreateGuestDeviceId()
    const visitorId = localStorage.getItem('visitor_id')
    if (visitorId) {
      config.headers['X-Session-ID'] = visitorId
    }
    return config
  },
  (error: AxiosError) => {
    return Promise.reject(error)
  }
)

// Response interceptor - handle errors uniformly
request.interceptors.response.use(
  (response: AxiosResponse) => {
    return response
  },
  async (error: AxiosError<{ detail: string }>) => {
    const authStore = useAuthStore()
    
    if (error.response) {
      const { status, data } = error.response
      
      switch (status) {
        case 401:
          // Token expired or invalid - try refresh
          if (authStore.refreshToken && !error.config?.url?.includes('/auth/refresh')) {
            try {
              const refreshResponse = await axios.post('/api/auth/refresh', {
                refresh_token: authStore.refreshToken
              })
              const { access_token } = refreshResponse.data
              authStore.setToken(access_token)
              
              // Retry original request
              if (error.config) {
                error.config.headers.Authorization = `Bearer ${access_token}`
                return axios(error.config)
              }
            } catch {
              // Refresh failed - only redirect if not on public page
              authStore.clearAuth()
              if (router.currentRoute.value.meta.public !== true) {
                router.push('/login')
                ElMessage.error('登录已过期，请重新登录')
              }
            }
          } else if (router.currentRoute.value.meta.public === true) {
            // On public pages (customer chat), clear expired guest token fully
            localStorage.removeItem('guest_token')
            localStorage.removeItem('visitor_id')
            authStore.clearAuth()
            // Don't redirect, don't show error — CustomerChat will re-request guest token
          } else {
            authStore.clearAuth()
            router.push('/login')
            ElMessage.error('未授权访问')
          }
          break
          
        case 403:
          ElMessage.error('权限不足')
          break
          
        case 404:
          ElMessage.error('资源不存在')
          break
          
        case 409:
          ElMessage.error(data?.detail || '资源已存在')
          break
          
        case 422:
          ElMessage.error('数据验证失败')
          break
          
        case 429:
          ElMessage.error('请求过于频繁，请稍后重试')
          break
          
        case 500:
        default:
          ElMessage.error(data?.detail || '服务器错误，请稍后重试')
          break
      }
    } else if (error.request) {
      if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
        ElMessage.error('请求超时，请稍后重试')
      } else {
        ElMessage.error('网络错误，请检查网络连接')
      }
    } else {
      ElMessage.error('请求配置错误')
    }
    
    return Promise.reject(error)
  }
)

export default request
