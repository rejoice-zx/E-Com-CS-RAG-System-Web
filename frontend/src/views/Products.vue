<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus, Search, Upload, Download, Delete, Edit, Folder, Refresh, EditPen, Close
} from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import {
  getProducts, createProduct, updateProduct, deleteProduct,
  importProducts, exportProducts, syncAllProductsToKnowledgeSSE, getProductCategories,
  deleteProductsByCategory
} from '@/api/product'
import type { Product } from '@/types'

// ── 分类（动态 + 自定义） ──
const categories = ref<string[]>([])
const activeCategory = ref('全部')
const newCatInput = ref('')
const showCatInput = ref(false)
const editingCat = ref<string | null>(null)
const editingCatValue = ref('')

async function loadCategories() {
  try {
    const res = await getProductCategories()
    const remote = res.data.categories || []
    const localOnly = categories.value.filter(c => c !== '全部' && !remote.includes(c))
    categories.value = ['全部', ...remote, ...localOnly]
  } catch { /* keep current */ }
}
function addCategory() {
  const v = newCatInput.value.trim()
  if (!v) return
  if (categories.value.includes(v)) { ElMessage.warning('分类已存在'); return }
  categories.value.push(v); newCatInput.value = ''; showCatInput.value = false
}
function startEditCat(cat: string) { editingCat.value = cat; editingCatValue.value = cat }
function confirmEditCat(oldCat: string) {
  const v = editingCatValue.value.trim()
  if (!v || v === oldCat) { editingCat.value = null; return }
  if (categories.value.includes(v)) { ElMessage.warning('分类已存在'); editingCat.value = null; return }
  const idx = categories.value.indexOf(oldCat)
  if (idx !== -1) categories.value[idx] = v
  if (activeCategory.value === oldCat) activeCategory.value = v
  editingCat.value = null
}
function deleteCat(cat: string) {
  categories.value = categories.value.filter(c => c !== cat)
  if (activeCategory.value === cat) { activeCategory.value = '全部'; loadList() }
}
function selectCategory(cat: string) { activeCategory.value = cat; currentPage.value = 1; loadList() }

// ── 列表 ──
const loading = ref(false)
const list = ref<Product[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const keyword = ref('')
const selected = ref<Product | null>(null)

async function loadList() {
  loading.value = true
  try {
    const res = await getProducts({
      page: currentPage.value, page_size: pageSize.value,
      category: activeCategory.value === '全部' ? undefined : activeCategory.value,
    })
    list.value = res.data.items; total.value = res.data.total
    if (selected.value && !list.value.find(i => i.id === selected.value!.id)) selected.value = null
  } catch (e: any) { ElMessage.error(e.response?.data?.detail || '加载失败') }
  finally { loading.value = false }
}
function handleSearch() { currentPage.value = 1; loadList() }

async function handleDeleteAllInCategory() {
  if (activeCategory.value === '全部') return
  try {
    await ElMessageBox.confirm(`确定删除分类「${activeCategory.value}」下的所有商品？此操作不可恢复。`, '确认删除', { type: 'warning', confirmButtonText: '全部删除', cancelButtonText: '取消' })
    const res = await deleteProductsByCategory(activeCategory.value)
    ElMessage.success(`已删除 ${res.data.deleted_count} 个商品`)
    selected.value = null; loadList(); loadCategories()
  } catch (e: any) { if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '删除失败') }
}
function handlePageChange(p: number) { currentPage.value = p; loadList() }

function selectItem(item: Product) {
  selected.value = { ...item }; editMode.value = false
  Object.assign(form, {
    name: item.name, price: item.price, category: item.category,
    description: item.description, specifications: { ...(item.specifications || {}) },
    stock: item.stock, keywords: [...(item.keywords || [])]
  })
}
async function handleDelete(item: Product, ev?: Event) {
  ev?.stopPropagation()
  try {
    await ElMessageBox.confirm(`确定删除「${item.name}」？`, '确认', { type: 'warning' })
    await deleteProduct(item.id); ElMessage.success('已删除')
    if (selected.value?.id === item.id) selected.value = null; loadList(); loadCategories()
  } catch (e: any) { if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '删除失败') }
}
function fmtPrice(p: number) { return `¥${p.toFixed(2)}` }
function stockTag(s: number) {
  if (s === 0) return { type: 'danger' as const, text: '缺货' }
  if (s < 10) return { type: 'warning' as const, text: '紧张' }
  return { type: 'success' as const, text: '有货' }
}

// ── 添加 ──
const addVisible = ref(false)
const addRef = ref<FormInstance>()
const addForm = reactive({ name: '', price: 0, category: '', description: '', specifications: {} as Record<string, string>, stock: 0, keywords: [] as string[] })
const addKw = ref(''); const addSK = ref(''); const addSV = ref('')
const addRules: FormRules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  price: [{ required: true, message: '请输入价格', trigger: 'blur' }],
  category: [{ required: true, message: '请选择分类', trigger: 'change' }],
  stock: [{ required: true, message: '请输入库存', trigger: 'blur' }]
}
function openAdd() {
  Object.assign(addForm, { name: '', price: 0, category: '', description: '', specifications: {}, stock: 0, keywords: [] })
  addKw.value = ''; addSK.value = ''; addSV.value = ''; addVisible.value = true
}
function pushAddKw() { const v = addKw.value.trim(); if (v && !addForm.keywords.includes(v)) { addForm.keywords.push(v); addKw.value = '' } }
function pushAddSpec() { const k = addSK.value.trim(), v = addSV.value.trim(); if (k && v) { addForm.specifications[k] = v; addSK.value = ''; addSV.value = '' } }
async function submitAdd() {
  if (!addRef.value) return
  try { await addRef.value.validate() } catch { return }
  try { await createProduct(addForm); ElMessage.success('添加成功'); addVisible.value = false; loadList(); loadCategories() }
  catch (e: any) { ElMessage.error(e.response?.data?.detail || '添加失败') }
}

// ── 详情编辑 ──
const form = reactive({ name: '', price: 0, category: '', description: '', specifications: {} as Record<string, string>, stock: 0, keywords: [] as string[] })
const editMode = ref(false)
const formKw = ref(''); const formSK = ref(''); const formSV = ref('')
function pushFormKw() { const v = formKw.value.trim(); if (v && !form.keywords.includes(v)) { form.keywords.push(v); formKw.value = '' } }
function pushFormSpec() { const k = formSK.value.trim(), v = formSV.value.trim(); if (k && v) { form.specifications[k] = v; formSK.value = ''; formSV.value = '' } }
async function saveEdit() {
  if (!selected.value) return
  try {
    await updateProduct(selected.value.id, { ...form }); ElMessage.success('已保存'); editMode.value = false
    const idx = list.value.findIndex(i => i.id === selected.value!.id)
    if (idx !== -1) { list.value[idx] = { ...list.value[idx], ...form }; selected.value = { ...list.value[idx] } }
    loadCategories()
  } catch (e: any) { ElMessage.error(e.response?.data?.detail || '保存失败') }
}
function cancelEdit() { editMode.value = false; if (selected.value) selectItem(selected.value) }

// ── 导入导出 & 同步 ──
const importVisible = ref(false); const importFile = ref<File | null>(null); const importLoading = ref(false)
const syncLoading = ref(false)

// 同步进度可视化
interface SyncLogItem { name: string; status: 'success' | 'fail' | 'pending'; error?: string }
const syncActive = ref(false)
const syncTotal = ref(0)
const syncCurrent = ref(0)
const syncSuccessCount = ref(0)
const syncFailCount = ref(0)
const syncLogs = ref<SyncLogItem[]>([])
const syncDone = ref(false)

function onFileChange(f: any) { importFile.value = f.raw }
async function doImport() {
  if (!importFile.value) { ElMessage.warning('请选择文件'); return }
  importLoading.value = true
  try {
    const data = JSON.parse(await importFile.value.text())
    if (!Array.isArray(data)) { ElMessage.error('格式错误'); return }
    await importProducts(data); ElMessage.success('导入成功'); importVisible.value = false; loadList(); loadCategories()
  } catch (e: any) { ElMessage.error(e.response?.data?.detail || '导入失败') }
  finally { importLoading.value = false }
}
async function doExport() {
  try {
    const res = await exportProducts()
    const data = Array.isArray(res.data) ? res.data : (res.data as any)?.items || []
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob)
    a.download = `products_${new Date().toISOString().split('T')[0]}.json`; a.click(); URL.revokeObjectURL(a.href)
    ElMessage.success('导出成功')
  } catch (e: any) { ElMessage.error(e.response?.data?.detail || '导出失败') }
}
function closeSyncPanel() { syncActive.value = false }
async function handleSync() {
  try {
    await ElMessageBox.confirm('将所有商品同步到知识库，已存在的会更新，确定继续？', '同步确认', { type: 'info' })
  } catch { return }

  // 重置状态
  syncLoading.value = true
  syncActive.value = true
  syncDone.value = false
  syncTotal.value = 0
  syncCurrent.value = 0
  syncSuccessCount.value = 0
  syncFailCount.value = 0
  syncLogs.value = []
  selected.value = null

  try {
    const reader = await syncAllProductsToKnowledgeSSE()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // 按行解析 SSE
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const evt = JSON.parse(line.slice(6))
          if (evt.type === 'start') {
            syncTotal.value = evt.total
          } else if (evt.type === 'progress') {
            syncCurrent.value = evt.current
            if (evt.status === 'success') {
              syncSuccessCount.value++
              syncLogs.value.push({ name: evt.name, status: 'success' })
            } else {
              syncFailCount.value++
              syncLogs.value.push({ name: evt.name, status: 'fail', error: evt.error })
            }
          } else if (evt.type === 'done') {
            syncDone.value = true
            syncSuccessCount.value = evt.success_count
            syncFailCount.value = evt.fail_count
          }
        } catch { /* skip malformed */ }
      }
    }

    if (syncFailCount.value > 0) {
      ElMessage.warning(`同步完成，成功 ${syncSuccessCount.value} 条，失败 ${syncFailCount.value} 条`)
    } else {
      ElMessage.success(`同步完成，成功 ${syncSuccessCount.value} 条`)
    }
  } catch (e: any) {
    ElMessage.error(e.message || '同步失败')
    syncDone.value = true
  } finally {
    syncLoading.value = false
  }
}

onMounted(() => { loadCategories(); loadList() })
</script>

<template>
  <div class="three-col">
    <!-- ====== 左栏：分类 ====== -->
    <aside class="col col-left">
      <div class="col-header"><span class="col-title">分类</span></div>
      <nav class="cat-nav">
        <div v-for="cat in categories" :key="cat" class="cat-item" :class="{ active: activeCategory === cat }">
          <template v-if="editingCat === cat && cat !== '全部'">
            <el-input v-model="editingCatValue" size="small" style="flex:1" @keyup.enter="confirmEditCat(cat)" />
            <el-button :icon="Edit" link size="small" @click="confirmEditCat(cat)" />
            <el-button :icon="Close" link size="small" @click="editingCat = null" />
          </template>
          <template v-else>
            <div class="cat-label" @click="selectCategory(cat)">
              <el-icon :size="15"><Folder /></el-icon>
              <span>{{ cat }}</span>
            </div>
            <div v-if="cat !== '全部'" class="cat-ops">
              <el-button :icon="EditPen" link size="small" @click.stop="startEditCat(cat)" />
              <el-button :icon="Delete" link size="small" type="danger" @click.stop="deleteCat(cat)" />
            </div>
          </template>
        </div>
      </nav>
      <div class="cat-add">
        <template v-if="showCatInput">
          <el-input v-model="newCatInput" size="small" placeholder="分类名称" @keyup.enter="addCategory" />
          <el-button size="small" type="primary" @click="addCategory">确定</el-button>
          <el-button size="small" @click="showCatInput = false">取消</el-button>
        </template>
        <el-button v-else :icon="Plus" size="small" text style="width:100%" @click="showCatInput = true">添加分类</el-button>
      </div>
      <div class="col-footer">
        <el-button text :icon="Upload" size="small" @click="importVisible = true">导入</el-button>
        <el-button text :icon="Download" size="small" @click="doExport">导出</el-button>
      </div>
    </aside>

    <!-- ====== 中栏：列表 ====== -->
    <section class="col col-center">
      <div class="col-header">
        <el-input v-model="keyword" placeholder="搜索商品…" clearable @keyup.enter="handleSearch" @clear="handleSearch">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-button type="primary" :icon="Plus" @click="openAdd">添加</el-button>
        <el-tooltip content="同步所有商品至知识库">
          <el-button type="success" :icon="Refresh" :loading="syncLoading" @click="handleSync">同步</el-button>
        </el-tooltip>
        <el-button v-if="activeCategory !== '全部'" type="danger" :icon="Delete" @click="handleDeleteAllInCategory">删除全部</el-button>
      </div>
      <div v-loading="loading" class="item-list">
        <div v-for="item in list" :key="item.id" class="item-card" :class="{ active: selected?.id === item.id }" @click="selectItem(item)">
          <div class="item-top">
            <span class="item-id">{{ item.id }}</span>
            <el-tag :type="stockTag(item.stock).type" size="small" effect="plain">{{ stockTag(item.stock).text }}</el-tag>
          </div>
          <p class="item-name">{{ item.name }}</p>
          <div class="item-bottom">
            <span class="item-price">{{ fmtPrice(item.price) }}</span>
            <div style="display:flex;align-items:center;gap:4px">
              <el-tag size="small" effect="plain">{{ item.category }}</el-tag>
              <el-button :icon="Delete" type="danger" text size="small" @click="handleDelete(item, $event)" />
            </div>
          </div>
        </div>
        <el-empty v-if="!loading && list.length === 0" description="暂无商品" :image-size="64" />
      </div>
      <div class="col-footer center">
        <el-pagination v-model:current-page="currentPage" :page-size="pageSize" :total="total" small background layout="prev, pager, next" @current-change="handlePageChange" />
      </div>
    </section>

    <!-- ====== 右栏：可滚动详情 + 固定底部编辑按钮 ====== -->
    <aside class="col col-right">
      <!-- 同步进度面板 -->
      <template v-if="syncActive">
        <div class="col-header">
          <span class="col-title">🔄 同步进度</span>
          <el-button v-if="syncDone" link size="small" @click="closeSyncPanel">关闭</el-button>
        </div>
        <div class="sync-panel">
          <!-- 进度条 -->
          <div class="sync-summary">
            <el-progress :percentage="syncTotal ? Math.round(syncCurrent / syncTotal * 100) : 0" :status="syncDone ? (syncFailCount > 0 ? 'warning' : 'success') : undefined" :stroke-width="18" style="margin-bottom:12px" />
            <div class="sync-stats">
              <span>总计 {{ syncTotal }}</span>
              <span class="sync-stat-ok">成功 {{ syncSuccessCount }}</span>
              <span v-if="syncFailCount" class="sync-stat-fail">失败 {{ syncFailCount }}</span>
              <span v-if="!syncDone" class="sync-stat-pending">进行中…</span>
              <span v-else class="sync-stat-done">已完成</span>
            </div>
          </div>
          <!-- 日志列表 -->
          <div class="sync-log-list">
            <div v-for="(log, i) in syncLogs" :key="i" class="sync-log-item" :class="log.status">
              <span class="sync-log-icon">{{ log.status === 'success' ? '✅' : '❌' }}</span>
              <span class="sync-log-name">{{ log.name }}</span>
              <span v-if="log.error" class="sync-log-err">{{ log.error }}</span>
            </div>
            <div v-if="!syncDone && syncCurrent < syncTotal" class="sync-log-item pending">
              <span class="sync-log-icon">⏳</span>
              <span class="sync-log-name">正在同步第 {{ syncCurrent + 1 }} / {{ syncTotal }} 个商品…</span>
            </div>
          </div>
        </div>
      </template>
      <!-- 商品详情 -->
      <template v-else-if="selected">
        <div class="col-header"><span class="col-title">商品详情 — {{ selected.id }}</span></div>

        <div class="detail-scroll">
          <el-card shadow="never" class="detail-block">
            <p class="meta-line"><span class="meta-label">ID</span>{{ selected.id }}</p>
            <p class="meta-line"><span class="meta-label">分类</span><el-tag size="small" effect="plain">{{ selected.category }}</el-tag></p>
            <p class="meta-line"><span class="meta-label">价格</span><span class="price-val">{{ fmtPrice(selected.price) }}</span></p>
            <p class="meta-line"><span class="meta-label">库存</span>{{ selected.stock }} <el-tag :type="stockTag(selected.stock).type" size="small">{{ stockTag(selected.stock).text }}</el-tag></p>
            <p class="meta-line"><span class="meta-label">关键词</span>
              <template v-if="(selected.keywords||[]).length"><el-tag v-for="kw in selected.keywords" :key="kw" size="small" type="info" round style="margin-right:4px">{{ kw }}</el-tag></template>
              <span v-else class="text-muted">无</span>
            </p>
          </el-card>
          <el-card shadow="never" class="detail-block">
            <template #header><span class="block-title">📝 描述</span></template>
            <el-input v-if="editMode" v-model="form.description" type="textarea" :rows="3" />
            <p v-else class="block-text pre">{{ selected.description || '暂无描述' }}</p>
          </el-card>
          <el-card shadow="never" class="detail-block">
            <template #header><span class="block-title">⚙️ 规格参数</span></template>
            <template v-if="editMode">
              <div style="display:flex;gap:6px;margin-bottom:8px">
                <el-input v-model="formSK" size="small" placeholder="参数名" style="width:100px" />
                <el-input v-model="formSV" size="small" placeholder="参数值" style="flex:1" />
                <el-button size="small" @click="pushFormSpec">添加</el-button>
              </div>
              <div style="display:flex;flex-wrap:wrap;gap:4px">
                <el-tag v-for="(v,k) in form.specifications" :key="k" closable size="small" @close="delete form.specifications[k as string]">{{ k }}: {{ v }}</el-tag>
              </div>
            </template>
            <template v-else>
              <div v-if="Object.keys(selected.specifications||{}).length" class="spec-view">
                <div v-for="(v,k) in selected.specifications" :key="k" class="spec-row"><span class="spec-k">{{ k }}</span>{{ v }}</div>
              </div>
              <p v-else class="block-text text-muted">暂无规格</p>
            </template>
          </el-card>
          <template v-if="editMode">
            <el-card shadow="never" class="detail-block">
              <template #header><span class="block-title">编辑基本信息</span></template>
              <div class="field-row"><span class="field-label">名称</span><el-input v-model="form.name" size="small" /></div>
              <div class="field-row"><span class="field-label">价格</span><el-input-number v-model="form.price" :min="0" :precision="2" size="small" style="width:100%" /></div>
              <div class="field-row"><span class="field-label">库存</span><el-input-number v-model="form.stock" :min="0" size="small" style="width:100%" /></div>
              <div class="field-row"><span class="field-label">分类</span>
                <el-select v-model="form.category" size="small" style="flex:1">
                  <el-option v-for="c in categories.filter(c=>c!=='全部')" :key="c" :label="c" :value="c" />
                </el-select>
              </div>
              <div class="field-row" style="margin-top:8px;align-items:flex-start"><span class="field-label">关键词</span>
                <div style="flex:1">
                  <div style="display:flex;gap:6px;margin-bottom:6px"><el-input v-model="formKw" size="small" placeholder="回车添加" @keyup.enter="pushFormKw" /><el-button size="small" @click="pushFormKw">添加</el-button></div>
                  <div style="display:flex;flex-wrap:wrap;gap:4px"><el-tag v-for="(kw,i) in form.keywords" :key="kw" closable size="small" @close="form.keywords.splice(i,1)">{{ kw }}</el-tag></div>
                </div>
              </div>
            </el-card>
          </template>
        </div>

        <!-- 固定底部：编辑/保存按钮 -->
        <div class="right-fixed-bottom">
          <div v-if="editMode" class="action-bar">
            <el-button type="primary" style="flex:1" @click="saveEdit">保存</el-button>
            <el-button style="flex:1" @click="cancelEdit">取消</el-button>
          </div>
          <el-button v-else type="primary" :icon="Edit" class="full-btn" @click="editMode = true">编辑商品</el-button>
        </div>
      </template>
      <div v-if="!syncActive && !selected" class="empty-detail"><el-empty description="选择一个商品查看详情" :image-size="64" /></div>
    </aside>

    <!-- 添加对话框 -->
    <el-dialog v-model="addVisible" title="添加商品" width="620px" destroy-on-close>
      <el-form ref="addRef" :model="addForm" :rules="addRules" label-width="80px">
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="名称" prop="name"><el-input v-model="addForm.name" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="分类" prop="category"><el-select v-model="addForm.category" style="width:100%"><el-option v-for="c in categories.filter(c=>c!=='全部')" :key="c" :label="c" :value="c" /></el-select></el-form-item></el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="价格" prop="price"><el-input-number v-model="addForm.price" :min="0" :precision="2" style="width:100%" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="库存" prop="stock"><el-input-number v-model="addForm.stock" :min="0" style="width:100%" /></el-form-item></el-col>
        </el-row>
        <el-form-item label="描述"><el-input v-model="addForm.description" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="规格">
          <div style="display:flex;gap:8px;margin-bottom:6px"><el-input v-model="addSK" placeholder="参数名" style="width:130px" /><el-input v-model="addSV" placeholder="参数值" style="width:170px" /><el-button @click="pushAddSpec">添加</el-button></div>
          <div style="display:flex;flex-wrap:wrap;gap:4px"><el-tag v-for="(v,k) in addForm.specifications" :key="k" closable @close="delete addForm.specifications[k as string]">{{ k }}: {{ v }}</el-tag></div>
        </el-form-item>
        <el-form-item label="关键词">
          <div style="display:flex;gap:8px;margin-bottom:6px"><el-input v-model="addKw" placeholder="回车添加" style="width:180px" @keyup.enter="pushAddKw" /><el-button @click="pushAddKw">添加</el-button></div>
          <div style="display:flex;flex-wrap:wrap;gap:4px"><el-tag v-for="(kw,i) in addForm.keywords" :key="kw" closable @close="addForm.keywords.splice(i,1)">{{ kw }}</el-tag></div>
        </el-form-item>
      </el-form>
      <template #footer><el-button @click="addVisible = false">取消</el-button><el-button type="primary" @click="submitAdd">确定</el-button></template>
    </el-dialog>

    <!-- 导入对话框 -->
    <el-dialog v-model="importVisible" title="导入商品" width="480px">
      <el-upload drag :auto-upload="false" :limit="1" accept=".json" :on-change="onFileChange">
        <el-icon class="el-icon--upload"><Upload /></el-icon>
        <div class="el-upload__text">拖拽 JSON 文件到此处，或<em>点击上传</em></div>
      </el-upload>
      <template #footer><el-button @click="importVisible = false">取消</el-button><el-button type="primary" :loading="importLoading" @click="doImport">导入</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.three-col { display: flex; height: calc(100vh - 60px); margin: -20px; background: var(--el-bg-color-page); overflow: hidden; }
.col { display: flex; flex-direction: column; overflow: hidden; }
.col-left  { width: 200px; min-width: 200px; background: var(--el-bg-color); border-right: 1px solid var(--el-border-color-lighter); }
.col-center { flex: 1; min-width: 0; border-right: 1px solid var(--el-border-color-lighter); background: var(--el-bg-color); }
.col-right { width: 380px; min-width: 340px; background: var(--el-bg-color); }

.col-header { display: flex; align-items: center; gap: 8px; padding: 14px 16px; border-bottom: 1px solid var(--el-border-color-lighter); flex-shrink: 0; }
.col-title { display: flex; align-items: center; gap: 6px; font-size: 14px; font-weight: 600; color: var(--el-text-color-primary); }
.col-footer { display: flex; align-items: center; justify-content: space-around; padding: 10px 12px; border-top: 1px solid var(--el-border-color-lighter); flex-shrink: 0; }
.col-footer.center { justify-content: center; }

.cat-nav { flex: 1; overflow-y: auto; padding: 4px 0; }
.cat-item { display: flex; align-items: center; gap: 4px; padding: 6px 12px; font-size: 13px; color: var(--el-text-color-regular); transition: background .15s; }
.cat-item:hover { background: var(--el-fill-color-light); }
.cat-item:hover .cat-ops { opacity: 1; }
.cat-item.active { color: var(--el-color-primary); background: var(--el-color-primary-light-9); }
.cat-item.active .cat-label { font-weight: 500; }
.cat-label { display: flex; align-items: center; gap: 8px; flex: 1; cursor: pointer; padding: 2px 0; }
.cat-ops { display: flex; gap: 0; opacity: 0; transition: opacity .15s; flex-shrink: 0; }
.cat-add { padding: 8px 12px; border-top: 1px solid var(--el-border-color-lighter); display: flex; gap: 6px; flex-wrap: wrap; }

.item-list { flex: 1; overflow-y: auto; padding: 10px 12px; }
.item-card { padding: 10px 14px; border-radius: 8px; margin-bottom: 6px; cursor: pointer; border: 1px solid transparent; transition: all .15s; }
.item-card:hover { background: var(--el-fill-color-light); }
.item-card.active { background: var(--el-color-primary-light-9); border-color: var(--el-color-primary-light-5); }
.item-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.item-id { font-size: 11px; color: var(--el-text-color-placeholder); font-family: monospace; }
.item-name { font-size: 13px; font-weight: 500; color: var(--el-text-color-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin: 0 0 6px; }
.item-bottom { display: flex; justify-content: space-between; align-items: center; }
.item-price { color: var(--el-color-danger); font-weight: 600; font-size: 14px; }

.detail-scroll { flex: 1; overflow-y: auto; padding: 12px 16px; }
.empty-detail { flex: 1; display: flex; align-items: center; justify-content: center; }

.right-fixed-bottom { flex-shrink: 0; padding: 12px 16px; border-top: 1px solid var(--el-border-color-lighter); }

.detail-block { margin-bottom: 12px; }
.detail-block :deep(.el-card__header) { padding: 10px 14px; font-size: 13px; }
.detail-block :deep(.el-card__body) { padding: 12px 14px; }
.meta-line { margin: 0 0 6px; font-size: 13px; color: var(--el-text-color-regular); display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.meta-label { font-weight: 600; min-width: 48px; color: var(--el-text-color-primary); }
.price-val { color: var(--el-color-danger); font-weight: 600; }
.block-title { font-size: 13px; font-weight: 600; }
.block-text { margin: 0; font-size: 13px; line-height: 1.65; color: var(--el-text-color-primary); }
.block-text.pre { white-space: pre-wrap; }
.text-muted { color: var(--el-text-color-placeholder); font-size: 13px; }

.spec-view { font-size: 13px; }
.spec-row { margin-bottom: 4px; display: flex; gap: 6px; }
.spec-k { color: var(--el-text-color-secondary); min-width: 60px; }

.field-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.field-label { font-size: 13px; color: var(--el-text-color-regular); min-width: 48px; white-space: nowrap; }
.action-bar { display: flex; gap: 8px; }
.full-btn { width: 100%; }

/* 同步进度面板 */
.sync-panel { flex: 1; overflow-y: auto; padding: 16px; }
.sync-summary { margin-bottom: 16px; }
.sync-stats { display: flex; gap: 14px; font-size: 13px; color: var(--el-text-color-regular); flex-wrap: wrap; }
.sync-stat-ok { color: var(--el-color-success); font-weight: 600; }
.sync-stat-fail { color: var(--el-color-danger); font-weight: 600; }
.sync-stat-pending { color: var(--el-color-primary); }
.sync-stat-done { color: var(--el-color-success); font-weight: 600; }
.sync-log-list { display: flex; flex-direction: column; gap: 4px; }
.sync-log-item { display: flex; align-items: flex-start; gap: 6px; padding: 6px 10px; border-radius: 6px; font-size: 13px; line-height: 1.5; background: var(--el-fill-color-lighter); }
.sync-log-item.success { background: var(--el-color-success-light-9); }
.sync-log-item.fail { background: var(--el-color-danger-light-9); }
.sync-log-item.pending { background: var(--el-color-primary-light-9); color: var(--el-color-primary); }
.sync-log-icon { flex-shrink: 0; }
.sync-log-name { flex: 1; min-width: 0; word-break: break-all; }
.sync-log-err { color: var(--el-color-danger); font-size: 12px; margin-left: 4px; }
</style>
