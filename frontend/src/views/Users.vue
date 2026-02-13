<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, Refresh, Check, Close, ArrowUp, ArrowDown } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import {
  getUsers,
  createUser,
  updateUser,
  deleteUser,
  getPendingRegistrations,
  approveRegistration,
  rejectRegistration,
  resetPassword
} from '@/api/users'
import { useAuthStore } from '@/stores/auth'
import type { User } from '@/types'
import type { PendingRegistration } from '@/api/users'

const authStore = useAuthStore()
const isSuperAdmin = computed(() => authStore.user?.username === 'admin')

// List state
const loading = ref(false)
const userList = ref<User[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(100)

// Filter state
const filters = reactive({
  role: '',
  isActive: undefined as boolean | undefined,
  username: ''
})

// Grouped users
const adminUsers = computed(() => userList.value.filter(u => u.role === 'admin'))
const csUsers = computed(() => userList.value.filter(u => u.role === 'cs'))
const customerUsers = computed(() => userList.value.filter(u => u.role === 'customer'))
const customerExpanded = ref(false)

// Pending registrations
const pendingList = ref<PendingRegistration[]>([])
const pendingLoading = ref(false)

// Dialog state
const dialogVisible = ref(false)
const dialogTitle = ref('添加用户')
const isEditing = ref(false)
const editingId = ref<number | null>(null)

// Form
const formRef = ref<FormInstance>()
const form = reactive({ username: '', password: '', display_name: '', email: '', role: 'cs' })
const rules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 50, message: '用户名长度应为3-50个字符', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少6个字符', trigger: 'blur' }
  ],
  display_name: [
    { required: true, message: '请输入显示名称', trigger: 'blur' },
    { min: 1, max: 100, message: '显示名称长度应为1-100个字符', trigger: 'blur' }
  ],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }]
}

// Password reset dialog
const passwordDialogVisible = ref(false)
const passwordUserId = ref<number | null>(null)
const newPassword = ref('')

async function loadUserList() {
  loading.value = true
  try {
    const response = await getUsers({
      page: currentPage.value,
      page_size: pageSize.value,
      role: filters.role || undefined,
      is_active: filters.isActive,
      username: filters.username || undefined
    })
    userList.value = response.data.items
    total.value = response.data.total
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '加载用户列表失败')
  } finally {
    loading.value = false
  }
}

async function loadPendingRegistrations() {
  pendingLoading.value = true
  try {
    const response = await getPendingRegistrations()
    pendingList.value = response.data
  } catch (error: any) {
    console.error('Failed to load pending registrations:', error)
  } finally {
    pendingLoading.value = false
  }
}

function handleSearch() { currentPage.value = 1; loadUserList() }
function handleReset() {
  filters.role = ''; filters.isActive = undefined; filters.username = ''
  currentPage.value = 1; loadUserList()
}

function openAddDialog() {
  dialogTitle.value = '添加用户'; isEditing.value = false; editingId.value = null; resetForm()
  dialogVisible.value = true
}
function openEditDialog(user: User) {
  dialogTitle.value = '编辑用户'; isEditing.value = true; editingId.value = user.id
  form.username = user.username; form.password = ''
  form.display_name = (user as any).display_name || user.displayName || ''
  form.email = user.email || ''; form.role = user.role
  dialogVisible.value = true
}
function resetForm() {
  form.username = ''; form.password = ''; form.display_name = ''; form.email = ''; form.role = 'cs'
  formRef.value?.resetFields()
}

async function handleSubmit() {
  if (!formRef.value) return
  try {
    if (isEditing.value) { await formRef.value.validateField(['username', 'display_name', 'role']) }
    else { await formRef.value.validate() }
  } catch { return }
  try {
    if (isEditing.value && editingId.value) {
      await updateUser(editingId.value, { display_name: form.display_name, email: form.email || undefined, role: form.role })
      ElMessage.success('更新成功')
    } else {
      await createUser({ username: form.username, password: form.password, display_name: form.display_name, email: form.email || undefined, role: form.role })
      ElMessage.success('添加成功')
    }
    dialogVisible.value = false; loadUserList()
  } catch (error: any) { ElMessage.error(error.response?.data?.detail || '操作失败') }
}

async function handleDelete(user: User) {
  try {
    await ElMessageBox.confirm(`确定要删除用户"${(user as any).display_name || user.displayName}"吗？`, '确认删除', { type: 'warning' })
    await deleteUser(user.id)
    ElMessage.success('删除成功'); loadUserList()
  } catch (error: any) {
    if (error !== 'cancel') ElMessage.error(error.response?.data?.detail || '删除失败')
  }
}

function canDeleteUser(user: User): boolean {
  // 不能删除自己
  if (user.id === authStore.user?.id) return false
  // 只有超级管理员(username=admin)才能删除管理员
  if (user.role === 'admin' && !isSuperAdmin.value) return false
  return true
}

async function handleToggleActive(user: User) {
  try {
    await updateUser(user.id, { is_active: !(user as any).is_active && !user.isActive })
    ElMessage.success(user.isActive || (user as any).is_active ? '已禁用' : '已启用'); loadUserList()
  } catch (error: any) { ElMessage.error(error.response?.data?.detail || '操作失败') }
}

async function handleApprove(reg: PendingRegistration) {
  try { await approveRegistration(reg.id); ElMessage.success('已通过审批'); loadPendingRegistrations(); loadUserList() }
  catch (error: any) { ElMessage.error(error.response?.data?.detail || '审批失败') }
}
async function handleReject(reg: PendingRegistration) {
  try {
    await ElMessageBox.confirm(`确定要拒绝用户"${reg.display_name}"的注册申请吗？`, '确认拒绝', { type: 'warning' })
    await rejectRegistration(reg.id); ElMessage.success('已拒绝'); loadPendingRegistrations()
  } catch (error: any) { if (error !== 'cancel') ElMessage.error(error.response?.data?.detail || '操作失败') }
}

function openPasswordDialog(user: User) { passwordUserId.value = user.id; newPassword.value = ''; passwordDialogVisible.value = true }
async function handleResetPassword() {
  if (!passwordUserId.value || !newPassword.value) { ElMessage.warning('请输入新密码'); return }
  if (newPassword.value.length < 6) { ElMessage.warning('密码至少6个字符'); return }
  try { await resetPassword(passwordUserId.value, newPassword.value); ElMessage.success('密码重置成功'); passwordDialogVisible.value = false }
  catch (error: any) { ElMessage.error(error.response?.data?.detail || '重置失败') }
}

function getRoleText(role: string): string { return role === 'admin' ? '管理员' : role === 'customer' ? '客户' : '客服' }
function getRoleType(role: string): string { return role === 'admin' ? 'danger' : role === 'customer' ? 'success' : 'primary' }
function formatDate(dateStr: string | undefined): string { if (!dateStr) return '-'; return new Date(dateStr).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) }
function isActive(user: User): boolean { return user.isActive || (user as any).is_active || false }

onMounted(() => { loadUserList(); loadPendingRegistrations() })
</script>

<template>
  <div class="users-container">
    <div class="page-header">
      <h1>用户管理</h1>
      <p class="page-description">管理系统用户和注册审批</p>
    </div>

    <!-- 待审批 -->
    <el-card v-if="pendingList.length > 0" class="section-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>待审批注册 ({{ pendingList.length }})</span>
          <el-button text :icon="Refresh" @click="loadPendingRegistrations" />
        </div>
      </template>
      <el-table v-loading="pendingLoading" :data="pendingList" stripe>
        <el-table-column prop="username" label="用户名" width="150" />
        <el-table-column prop="display_name" label="显示名称" width="150" />
        <el-table-column prop="email" label="邮箱" min-width="200" />
        <el-table-column label="申请时间" width="180">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button type="success" text size="small" :icon="Check" @click="handleApprove(row)">通过</el-button>
            <el-button type="danger" text size="small" :icon="Close" @click="handleReject(row)">拒绝</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 搜索栏 -->
    <el-card class="section-card" shadow="never">
      <div class="toolbar">
        <div class="toolbar-left">
          <el-input v-model="filters.username" placeholder="搜索用户名" clearable style="width: 160px" :prefix-icon="Search" @keyup.enter="handleSearch" />
          <el-select v-model="filters.role" placeholder="选择角色" clearable style="width: 140px">
            <el-option label="管理员" value="admin" />
            <el-option label="客服" value="cs" />
            <el-option label="客户" value="customer" />
          </el-select>
          <el-select v-model="filters.isActive" placeholder="选择状态" clearable style="width: 140px">
            <el-option label="已启用" :value="true" />
            <el-option label="已禁用" :value="false" />
          </el-select>
          <el-button type="primary" :icon="Search" @click="handleSearch">搜索</el-button>
          <el-button :icon="Refresh" @click="handleReset">重置</el-button>
        </div>
        <div class="toolbar-right">
          <el-button type="primary" :icon="Plus" @click="openAddDialog">添加用户</el-button>
        </div>
      </div>
    </el-card>

    <!-- 管理员列表 -->
    <el-card v-if="adminUsers.length > 0" class="section-card" shadow="never">
      <template #header>
        <span>管理员 ({{ adminUsers.length }})</span>
      </template>
      <el-table :data="adminUsers" stripe v-loading="loading">
        <el-table-column type="index" label="序号" width="60" />
        <el-table-column prop="username" label="用户名" width="140" />
        <el-table-column label="显示名称" width="140">
          <template #default="{ row }">{{ (row as any).display_name || row.displayName || '-' }}</template>
        </el-table-column>
        <el-table-column label="角色" width="90">
          <template #default="{ row }"><el-tag :type="getRoleType(row.role)" size="small">{{ getRoleText(row.role) }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="email" label="邮箱" min-width="180" />
        <el-table-column label="状态" width="80">
          <template #default="{ row }"><el-tag :type="isActive(row) ? 'success' : 'info'" size="small">{{ isActive(row) ? '启用' : '禁用' }}</el-tag></template>
        </el-table-column>
        <el-table-column label="最后登录" width="170">
          <template #default="{ row }">{{ formatDate((row as any).last_login || row.lastLogin) }}</template>
        </el-table-column>
        <el-table-column label="操作" min-width="200" fixed="right">
          <template #default="{ row }">
            <div class="action-btns">
              <el-link type="primary" :underline="false" @click="openEditDialog(row)">编辑</el-link>
              <el-link type="warning" :underline="false" @click="openPasswordDialog(row)">重置密码</el-link>
              <el-link :type="isActive(row) ? 'info' : 'success'" :underline="false" @click="handleToggleActive(row)">{{ isActive(row) ? '禁用' : '启用' }}</el-link>
              <el-link v-if="canDeleteUser(row)" type="danger" :underline="false" @click="handleDelete(row)">删除</el-link>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 客服列表 -->
    <el-card v-if="csUsers.length > 0" class="section-card" shadow="never">
      <template #header>
        <span>客服 ({{ csUsers.length }})</span>
      </template>
      <el-table :data="csUsers" stripe v-loading="loading">
        <el-table-column type="index" label="序号" width="60" />
        <el-table-column prop="username" label="用户名" width="140" />
        <el-table-column label="显示名称" width="140">
          <template #default="{ row }">{{ (row as any).display_name || row.displayName || '-' }}</template>
        </el-table-column>
        <el-table-column label="角色" width="90">
          <template #default="{ row }"><el-tag :type="getRoleType(row.role)" size="small">{{ getRoleText(row.role) }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="email" label="邮箱" min-width="180" />
        <el-table-column label="状态" width="80">
          <template #default="{ row }"><el-tag :type="isActive(row) ? 'success' : 'info'" size="small">{{ isActive(row) ? '启用' : '禁用' }}</el-tag></template>
        </el-table-column>
        <el-table-column label="最后登录" width="170">
          <template #default="{ row }">{{ formatDate((row as any).last_login || row.lastLogin) }}</template>
        </el-table-column>
        <el-table-column label="操作" min-width="200" fixed="right">
          <template #default="{ row }">
            <div class="action-btns">
              <el-link type="primary" :underline="false" @click="openEditDialog(row)">编辑</el-link>
              <el-link type="warning" :underline="false" @click="openPasswordDialog(row)">重置密码</el-link>
              <el-link :type="isActive(row) ? 'info' : 'success'" :underline="false" @click="handleToggleActive(row)">{{ isActive(row) ? '禁用' : '启用' }}</el-link>
              <el-link v-if="canDeleteUser(row)" type="danger" :underline="false" @click="handleDelete(row)">删除</el-link>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 客户列表（可折叠） -->
    <el-card v-if="customerUsers.length > 0" class="section-card" shadow="never">
      <template #header>
        <div class="card-header clickable" @click="customerExpanded = !customerExpanded">
          <span>客户 ({{ customerUsers.length }})</span>
          <el-icon v-if="customerExpanded"><ArrowUp /></el-icon>
          <el-icon v-else><ArrowDown /></el-icon>
        </div>
      </template>
      <el-collapse-transition>
        <div v-show="customerExpanded">
          <el-table :data="customerUsers" stripe v-loading="loading">
            <el-table-column type="index" label="序号" width="60" />
            <el-table-column prop="username" label="用户名" width="140" />
            <el-table-column label="显示名称" width="140">
              <template #default="{ row }">{{ (row as any).display_name || row.displayName || '-' }}</template>
            </el-table-column>
            <el-table-column label="角色" width="90">
              <template #default="{ row }"><el-tag :type="getRoleType(row.role)" size="small">{{ getRoleText(row.role) }}</el-tag></template>
            </el-table-column>
            <el-table-column prop="email" label="邮箱" min-width="180" />
            <el-table-column label="状态" width="80">
              <template #default="{ row }"><el-tag :type="isActive(row) ? 'success' : 'info'" size="small">{{ isActive(row) ? '启用' : '禁用' }}</el-tag></template>
            </el-table-column>
            <el-table-column label="最后登录" width="170">
              <template #default="{ row }">{{ formatDate((row as any).last_login || row.lastLogin) }}</template>
            </el-table-column>
            <el-table-column label="操作" min-width="200" fixed="right">
              <template #default="{ row }">
                <div class="action-btns">
                  <el-link type="primary" :underline="false" @click="openEditDialog(row)">编辑</el-link>
                  <el-link type="warning" :underline="false" @click="openPasswordDialog(row)">重置密码</el-link>
                  <el-link :type="isActive(row) ? 'info' : 'success'" :underline="false" @click="handleToggleActive(row)">{{ isActive(row) ? '禁用' : '启用' }}</el-link>
                  <el-link v-if="canDeleteUser(row)" type="danger" :underline="false" @click="handleDelete(row)">删除</el-link>
                </div>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-collapse-transition>
    </el-card>

    <!-- 添加/编辑用户对话框 -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="480px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" :disabled="isEditing" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item v-if="!isEditing" label="密码" prop="password">
          <el-input v-model="form.password" type="password" show-password placeholder="请输入密码" />
        </el-form-item>
        <el-form-item label="显示名称" prop="display_name">
          <el-input v-model="form.display_name" placeholder="请输入显示名称" />
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="form.email" placeholder="请输入邮箱（可选）" />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="form.role" style="width: 100%">
            <el-option label="管理员" value="admin" />
            <el-option label="客服" value="cs" />
            <el-option label="客户" value="customer" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>

    <!-- 重置密码对话框 -->
    <el-dialog v-model="passwordDialogVisible" title="重置密码" width="400px" destroy-on-close>
      <el-form label-width="80px">
        <el-form-item label="新密码">
          <el-input v-model="newPassword" type="password" show-password placeholder="请输入新密码（至少6个字符）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="passwordDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleResetPassword">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.users-container {
  padding: 20px;
}
.page-header {
  margin-bottom: 20px;
}
.page-header h1 {
  margin: 0 0 4px 0;
  font-size: 22px;
  font-weight: 600;
}
.page-description {
  margin: 0;
  color: #909399;
  font-size: 14px;
}
.section-card {
  margin-bottom: 16px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
}
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.card-header.clickable {
  cursor: pointer;
  user-select: none;
}
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
}
.toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.action-btns {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: nowrap;
}
.action-btns .el-link {
  font-size: 12px;
  padding: 4px 8px;
  border: 1px solid currentColor;
  border-radius: 4px;
  transition: all 0.2s;
}
.action-btns .el-link:hover {
  opacity: 0.8;
}
</style>
