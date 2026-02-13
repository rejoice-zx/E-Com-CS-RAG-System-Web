<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import { MainLayout } from '@/components/layout'
import { useSettingsStore } from '@/stores/settings'

const route = useRoute()
const settingsStore = useSettingsStore()

// Check if current route is public (like login)
const isPublicRoute = computed(() => route.meta.public === true)

// Initialize theme on mount
onMounted(() => {
  const theme = settingsStore.theme
  document.documentElement.setAttribute('data-theme', theme)
  if (theme === 'dark') {
    document.documentElement.classList.add('dark')
  }
})
</script>

<template>
  <!-- Public routes (login) render without layout -->
  <RouterView v-if="isPublicRoute" />
  
  <!-- Protected routes render with main layout -->
  <MainLayout v-else>
    <RouterView />
  </MainLayout>
</template>

<style>
:root {
  --bg-color: #f5f7fa;
  --sidebar-bg: #fff;
  --topbar-bg: #fff;
  --border-color: #e4e7ed;
  --text-color: #303133;
  --text-secondary: #909399;
  --hover-bg: #f5f7fa;
}

:root.dark {
  --bg-color: #141414;
  --sidebar-bg: #1d1e1f;
  --topbar-bg: #1d1e1f;
  --border-color: #414243;
  --text-color: #e5eaf3;
  --text-secondary: #a3a6ad;
  --hover-bg: #262727;
}

* {
  box-sizing: border-box;
}

html, body {
  margin: 0;
  padding: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
}

#app {
  width: 100%;
  min-height: 100vh;
}

/* Element Plus Dark Mode Overrides */
html.dark {
  --el-bg-color: #1d1e1f;
  --el-bg-color-page: #141414;
  --el-bg-color-overlay: #1d1e1f;
  --el-text-color-primary: #e5eaf3;
  --el-text-color-regular: #cfd3dc;
  --el-text-color-secondary: #a3a6ad;
  --el-text-color-placeholder: #8d9095;
  --el-border-color: #414243;
  --el-border-color-light: #363637;
  --el-border-color-lighter: #2d2d2d;
  --el-fill-color: #262727;
  --el-fill-color-light: #1d1e1f;
  --el-fill-color-lighter: #262727;
  --el-fill-color-blank: #1d1e1f;
}

html.dark .el-menu {
  background-color: var(--sidebar-bg);
  border-right: none;
}

html.dark .el-menu-item {
  color: var(--text-color);
}

html.dark .el-menu-item:hover {
  background-color: var(--hover-bg);
}

html.dark .el-menu-item.is-active {
  color: var(--el-color-primary);
}

html.dark .el-drawer {
  background-color: var(--sidebar-bg);
}

html.dark .el-card {
  background-color: var(--sidebar-bg);
  border-color: var(--border-color);
}

html.dark .el-table {
  --el-table-bg-color: var(--sidebar-bg);
  --el-table-tr-bg-color: var(--sidebar-bg);
  --el-table-header-bg-color: var(--bg-color);
  --el-table-row-hover-bg-color: var(--hover-bg);
  --el-table-border-color: var(--border-color);
}

html.dark .el-input__wrapper {
  background-color: var(--bg-color);
}

html.dark .el-select__wrapper {
  background-color: var(--bg-color);
}

html.dark .el-pagination {
  --el-pagination-bg-color: var(--sidebar-bg);
  --el-pagination-button-bg-color: var(--sidebar-bg);
  --el-pagination-hover-color: var(--el-color-primary);
}
</style>
