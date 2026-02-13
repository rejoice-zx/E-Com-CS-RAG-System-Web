import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw, NavigationGuardNext, RouteLocationNormalized } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

// Extend RouteMeta type
declare module 'vue-router' {
  interface RouteMeta {
    public?: boolean
    roles?: string[]
    title?: string
    icon?: string
    hidden?: boolean
  }
}

// Menu item interface for sidebar navigation
export interface MenuItem {
  path: string
  name: string
  title: string
  icon?: string
  roles: string[]
}

// Route definitions with meta information
const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { 
      public: true,
      title: '登录',
      hidden: true
    }
  },
  {
    path: '/',
    name: 'CustomerChat',
    component: () => import('@/views/CustomerChat.vue'),
    meta: { 
      public: true,
      title: '智能客服',
      hidden: true
    }
  },
  {
    path: '/workbench',
    name: 'Workbench',
    component: () => import('@/views/Workbench.vue'),
    meta: { 
      roles: ['admin'],
      title: 'AI工作台',
      icon: 'Monitor'
    }
  },
  {
    path: '/knowledge',
    name: 'Knowledge',
    component: () => import('@/views/Knowledge.vue'),
    meta: { 
      roles: ['admin'],
      title: '知识库管理',
      icon: 'Collection'
    }
  },
  {
    path: '/products',
    name: 'Products',
    component: () => import('@/views/Products.vue'),
    meta: { 
      roles: ['admin', 'cs'],
      title: '商品管理',
      icon: 'Goods'
    }
  },
  {
    path: '/human-service',
    name: 'HumanService',
    component: () => import('@/views/HumanService.vue'),
    meta: { 
      roles: ['admin', 'cs'],
      title: '人工客服',
      icon: 'Service'
    }
  },
  {
    path: '/statistics',
    name: 'Statistics',
    component: () => import('@/views/Statistics.vue'),
    meta: { 
      roles: ['admin'],
      title: '数据统计',
      icon: 'DataAnalysis'
    }
  },
  {
    path: '/performance',
    name: 'Performance',
    component: () => import('@/views/Performance.vue'),
    meta: { 
      roles: ['admin'],
      title: '性能监控',
      icon: 'Odometer'
    }
  },
  {
    path: '/logs',
    name: 'Logs',
    component: () => import('@/views/Logs.vue'),
    meta: { 
      roles: ['admin'],
      title: '日志管理',
      icon: 'Document'
    }
  },
  {
    path: '/users',
    name: 'Users',
    component: () => import('@/views/Users.vue'),
    meta: { 
      roles: ['admin'],
      title: '用户管理',
      icon: 'User'
    }
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('@/views/Settings.vue'),
    meta: { 
      roles: ['admin'],
      title: '系统设置',
      icon: 'Setting'
    }
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    redirect: '/',
    meta: { hidden: true }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// Navigation guard for authentication and authorization
router.beforeEach(async (
  to: RouteLocationNormalized,
  _from: RouteLocationNormalized,
  next: NavigationGuardNext
) => {
  const authStore = useAuthStore()
  
  // Public routes don't require authentication
  if (to.meta.public) {
    // If already authenticated and trying to access login, redirect to appropriate home
    if (authStore.isAuthenticated && to.path === '/login') {
      const landing = getFirstAccessibleRoute(authStore.userRole) || '/'
      next(landing)
      return
    }
    next()
    return
  }
  
  // Check if user is authenticated
  if (!authStore.isAuthenticated) {
    next({
      path: '/login',
      query: { redirect: to.fullPath }
    })
    return
  }
  
  // Initialize auth if needed (fetch user info if not loaded)
  if (!authStore.user) {
    const success = await authStore.fetchCurrentUser()
    if (!success) {
      next('/login')
      return
    }
  }
  
  // Check role-based access
  const requiredRoles = to.meta.roles as string[] | undefined
  if (requiredRoles && requiredRoles.length > 0) {
    if (!authStore.hasRole(requiredRoles)) {
      // User doesn't have required role - redirect to first accessible route
      const accessibleRoute = getFirstAccessibleRoute(authStore.userRole)
      if (accessibleRoute) {
        next(accessibleRoute)
      } else {
        // No accessible routes - logout
        authStore.logout()
        next('/login')
      }
      return
    }
  }
  
  next()
})

// Helper function to get first accessible route for a role
function getFirstAccessibleRoute(role: string | null): string | null {
  if (!role) return null
  
  // 管理员默认进入AI工作台，客服默认进入人工客服，客户默认进入客服聊天
  if (role === 'admin') return '/workbench'
  if (role === 'cs') return '/human-service'
  if (role === 'customer') return '/'
  
  for (const route of routes) {
    if (route.meta?.roles?.includes(role) && !route.meta?.hidden) {
      return route.path
    }
  }
  return null
}

// Get menu items filtered by user role
export function getMenuItems(role: string | null): MenuItem[] {
  if (!role) return []
  
  return routes
    .filter(route => {
      // Exclude hidden routes and routes without roles
      if (route.meta?.hidden) return false
      if (!route.meta?.roles) return false
      // Check if user has required role
      return route.meta.roles.includes(role)
    })
    .map(route => ({
      path: route.path,
      name: route.name as string,
      title: route.meta?.title || route.name as string,
      icon: route.meta?.icon,
      roles: route.meta?.roles || []
    }))
}

// Get all routes (for admin purposes)
export function getAllRoutes(): RouteRecordRaw[] {
  return routes.filter(route => !route.meta?.hidden && route.meta?.roles)
}

export default router
