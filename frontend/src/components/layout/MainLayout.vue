<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Expand,
  Fold,
  SwitchButton,
  Moon,
  Sunny
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useSettingsStore } from '@/stores/settings'
import { getMenuItems, type MenuItem } from '@/router'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const settingsStore = useSettingsStore()

// Sidebar state
const isCollapsed = ref(false)
const isMobile = ref(false)
const mobileDrawerVisible = ref(false)

// Get menu items based on user role
const menuItems = computed<MenuItem[]>(() => {
  return getMenuItems(authStore.userRole)
})

// Current active menu
const activeMenu = computed(() => route.path)

// User display name
const userDisplayName = computed(() => {
  return authStore.user?.displayName || authStore.user?.username || '用户'
})

// Theme
const isDarkTheme = computed(() => settingsStore.theme === 'dark')

// Toggle sidebar collapse
function toggleSidebar() {
  if (isMobile.value) {
    mobileDrawerVisible.value = !mobileDrawerVisible.value
  } else {
    isCollapsed.value = !isCollapsed.value
  }
}

// Handle menu select
function handleMenuSelect(path: string) {
  router.push(path)
  if (isMobile.value) {
    mobileDrawerVisible.value = false
  }
}

// Toggle theme
function toggleTheme() {
  const newTheme = isDarkTheme.value ? 'light' : 'dark'
  settingsStore.setTheme(newTheme)
  applyTheme(newTheme)
}

// Apply theme to document
function applyTheme(theme: 'light' | 'dark') {
  document.documentElement.setAttribute('data-theme', theme)
  if (theme === 'dark') {
    document.documentElement.classList.add('dark')
  } else {
    document.documentElement.classList.remove('dark')
  }
}

// Handle logout
function handleLogout() {
  authStore.logout()
  ElMessage.success('已退出登录')
}

// Check screen size for responsive layout
function checkScreenSize() {
  isMobile.value = window.innerWidth < 768
  if (isMobile.value) {
    isCollapsed.value = true
  }
}

// Initialize
onMounted(() => {
  checkScreenSize()
  window.addEventListener('resize', checkScreenSize)
  // Apply saved theme
  applyTheme(settingsStore.theme)
})

// Watch for route changes to close mobile drawer
watch(() => route.path, () => {
  if (isMobile.value) {
    mobileDrawerVisible.value = false
  }
})
</script>

<template>
  <div
    class="main-layout"
    :class="{ 'dark-theme': isDarkTheme }"
  >
    <!-- Desktop Sidebar -->
    <aside
      v-if="!isMobile"
      class="sidebar"
      :class="{ 'sidebar-collapsed': isCollapsed }"
    >
      <div class="sidebar-header">
        <div class="logo-container">
          <img src="/favicon.svg" alt="logo" class="logo-icon" style="width: 28px; height: 28px;" />
          <span
            v-show="!isCollapsed"
            class="logo-text"
          >智能客服</span>
        </div>
      </div>
      
      <el-menu
        :default-active="activeMenu"
        :collapse="isCollapsed"
        :collapse-transition="false"
        class="sidebar-menu"
        @select="handleMenuSelect"
      >
        <el-menu-item
          v-for="item in menuItems"
          :key="item.path"
          :index="item.path"
        >
          <el-icon v-if="item.icon">
            <component :is="item.icon" />
          </el-icon>
          <template #title>
            {{ item.title }}
          </template>
        </el-menu-item>
      </el-menu>
    </aside>

    <!-- Mobile Drawer -->
    <el-drawer
      v-if="isMobile"
      v-model="mobileDrawerVisible"
      direction="ltr"
      :with-header="false"
      size="240px"
      class="mobile-drawer"
    >
      <div class="sidebar-header">
        <div class="logo-container">
          <img src="/favicon.svg" alt="logo" class="logo-icon" style="width: 28px; height: 28px;" />
          <span class="logo-text">智能客服</span>
        </div>
      </div>
      
      <el-menu
        :default-active="activeMenu"
        class="sidebar-menu"
        @select="handleMenuSelect"
      >
        <el-menu-item
          v-for="item in menuItems"
          :key="item.path"
          :index="item.path"
        >
          <el-icon v-if="item.icon">
            <component :is="item.icon" />
          </el-icon>
          <template #title>
            {{ item.title }}
          </template>
        </el-menu-item>
      </el-menu>
    </el-drawer>

    <!-- Main Content Area -->
    <div
      class="main-container"
      :class="{ 'main-expanded': isCollapsed && !isMobile }"
    >
      <!-- Top Bar -->
      <header class="top-bar">
        <div class="top-bar-left">
          <el-button
            class="toggle-btn"
            :icon="isCollapsed || isMobile ? Expand : Fold"
            @click="toggleSidebar"
          />
          <span class="page-title">{{ route.meta.title || '首页' }}</span>
        </div>
        
        <div class="top-bar-right">
          <!-- Theme Toggle -->
          <el-tooltip :content="isDarkTheme ? '切换亮色主题' : '切换暗色主题'">
            <el-button
              class="theme-btn"
              :icon="isDarkTheme ? Sunny : Moon"
              @click="toggleTheme"
            />
          </el-tooltip>
          
          <!-- User Dropdown -->
          <el-dropdown
            trigger="click"
            @command="handleLogout"
          >
            <div class="user-info">
              <el-avatar
                :size="32"
                class="user-avatar"
              >
                {{ userDisplayName.charAt(0).toUpperCase() }}
              </el-avatar>
              <span class="user-name">{{ userDisplayName }}</span>
              <el-tag
                size="small"
                :type="authStore.isAdmin ? 'danger' : 'info'"
              >
                {{ authStore.isAdmin ? '管理员' : '客服' }}
              </el-tag>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item
                  :icon="SwitchButton"
                  command="logout"
                >
                  退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>

      <!-- Page Content -->
      <main class="page-content">
        <slot />
      </main>
    </div>
  </div>
</template>

<style scoped>
.main-layout {
  display: flex;
  min-height: 100vh;
  background-color: var(--bg-color, #f5f7fa);
}

/* Sidebar Styles */
.sidebar {
  width: 220px;
  background-color: var(--sidebar-bg, #fff);
  border-right: 1px solid var(--border-color, #e4e7ed);
  display: flex;
  flex-direction: column;
  transition: width 0.3s ease;
  position: fixed;
  left: 0;
  top: 0;
  bottom: 0;
  z-index: 100;
}

.sidebar-collapsed {
  width: 64px;
}

.sidebar-header {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-bottom: 1px solid var(--border-color, #e4e7ed);
  padding: 0 16px;
}

.logo-container {
  display: flex;
  align-items: center;
  gap: 10px;
  overflow: hidden;
}

.logo-icon {
  color: var(--el-color-primary);
  flex-shrink: 0;
}

.logo-text {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-color, #303133);
  white-space: nowrap;
}

.sidebar-menu {
  flex: 1;
  border-right: none;
  overflow-y: auto;
}

.sidebar-menu:not(.el-menu--collapse) {
  width: 100%;
}

/* Main Container */
.main-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  margin-left: 220px;
  transition: margin-left 0.3s ease;
  min-height: 100vh;
}

.main-expanded {
  margin-left: 64px;
}

/* Top Bar */
.top-bar {
  height: 60px;
  background-color: var(--topbar-bg, #fff);
  border-bottom: 1px solid var(--border-color, #e4e7ed);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  position: sticky;
  top: 0;
  z-index: 99;
}

.top-bar-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.toggle-btn {
  border: none;
  background: transparent;
  font-size: 18px;
}

.page-title {
  font-size: 18px;
  font-weight: 500;
  color: var(--text-color, #303133);
}

.top-bar-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.theme-btn {
  border: none;
  background: transparent;
  font-size: 18px;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 8px;
  transition: background-color 0.2s;
}

.user-info:hover {
  background-color: var(--hover-bg, #f5f7fa);
}

.user-avatar {
  background-color: var(--el-color-primary);
  color: #fff;
}

.user-name {
  font-size: 14px;
  color: var(--text-color, #303133);
}

/* Page Content */
.page-content {
  flex: 1;
  padding: 20px;
  overflow-y: auto;
}

/* Mobile Styles */
@media (max-width: 767px) {
  .main-container {
    margin-left: 0;
  }
  
  .main-expanded {
    margin-left: 0;
  }
  
  .user-name {
    display: none;
  }
  
  .page-title {
    font-size: 16px;
  }
}

/* Dark Theme */
.dark-theme {
  --bg-color: #141414;
  --sidebar-bg: #1d1e1f;
  --topbar-bg: #1d1e1f;
  --border-color: #414243;
  --text-color: #e5eaf3;
  --hover-bg: #262727;
}

.dark-theme .sidebar-menu {
  background-color: var(--sidebar-bg);
}

.dark-theme :deep(.el-menu) {
  background-color: var(--sidebar-bg);
  border-right: none;
}

.dark-theme :deep(.el-menu-item) {
  color: var(--text-color);
}

.dark-theme :deep(.el-menu-item:hover) {
  background-color: var(--hover-bg);
}

.dark-theme :deep(.el-menu-item.is-active) {
  color: var(--el-color-primary);
  background-color: var(--hover-bg);
}

/* Mobile Drawer Dark Theme */
.dark-theme :deep(.el-drawer) {
  background-color: var(--sidebar-bg);
}
</style>
