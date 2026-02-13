<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus, Search, Upload, Download, Delete, Edit, Setting, Refresh, Folder, EditPen, Close
} from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import {
  getKnowledgeList, createKnowledge, updateKnowledge, deleteKnowledge,
  importKnowledge, exportKnowledge, getIndexStatus, getKnowledgeCategories,
  deleteKnowledgeByCategory, rebuildIndexSSE
} from '@/api/knowledge'
import { getSettings, updateSettings } from '@/api/settings'
import type { KnowledgeItem, IndexStatus } from '@/types'

// ── 分类（动态从后端加载 + 本地自定义） ──
const categories = ref<string[]>([])
const activeCategory = ref('全部')
const newCatInput = ref('')
const showCatInput = ref(false)
const editingCat = ref<string | null>(null)
const editingCatValue = ref('')

async function loadCategories() {
  try {
    const res = await getKnowledgeCategories()
    const remote = res.data.categories || []
    // 合并：保留本地自定义的（不在远程中的）
    const localOnly = categories.value.filter(c => c !== '全部' && !remote.includes(c))
    categories.value = ['全部', ...remote, ...localOnly]
  } catch { /* keep current */ }
}

function addCategory() {
  const v = newCatInput.value.trim()
  if (!v) return
  if (categories.value.includes(v)) { ElMessage.warning('分类已存在'); return }
  categories.value.push(v)
  newCatInput.value = ''; showCatInput.value = false
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
const list = ref<KnowledgeItem[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const keyword = ref('')
const selected = ref<KnowledgeItem | null>(null)

async function loadList() {
  loading.value = true
  try {
    const res = await getKnowledgeList({
      page: currentPage.value, page_size: pageSize.value,
      category: activeCategory.value === '全部' ? undefined : activeCategory.value,
      keyword: keyword.value || undefined
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
    await ElMessageBox.confirm(`确定删除分类「${activeCategory.value}」下的所有知识条目？此操作不可恢复。`, '确认删除', { type: 'warning', confirmButtonText: '全部删除', cancelButtonText: '取消' })
    const res = await deleteKnowledgeByCategory(activeCategory.value)
    ElMessage.success(`已删除 ${res.data.deleted_count} 条知识`)
    selected.value = null; loadList(); loadIndexStatus(); loadCategories()
  } catch (e: any) { if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '删除失败') }
}
function handlePageChange(p: number) { currentPage.value = p; loadList() }

function selectItem(item: KnowledgeItem) {
  selected.value = { ...item }; editMode.value = false
  form.question = item.question; form.answer = item.answer
  form.keywords = [...(item.keywords || [])]; form.category = item.category
}

async function handleDelete(item: KnowledgeItem, ev?: Event) {
  ev?.stopPropagation()
  try {
    await ElMessageBox.confirm(`确定删除「${item.question.substring(0, 20)}…」？`, '确认', { type: 'warning' })
    await deleteKnowledge(item.id); ElMessage.success('已删除')
    if (selected.value?.id === item.id) selected.value = null
    loadList(); loadIndexStatus(); loadCategories()
  } catch (e: any) { if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '删除失败') }
}

// ── 添加 ──
const addVisible = ref(false)
const addRef = ref<FormInstance>()
const addForm = reactive({ question: '', answer: '', keywords: [] as string[], category: '通用' })
const addKw = ref('')
const addRules: FormRules = {
  question: [{ required: true, message: '请输入问题', trigger: 'blur' }],
  answer: [{ required: true, message: '请输入答案', trigger: 'blur' }],
  category: [{ required: true, message: '请选择分类', trigger: 'change' }]
}
function openAdd() {
  Object.assign(addForm, { question: '', answer: '', keywords: [], category: '通用' })
  addKw.value = ''; addVisible.value = true
}
function pushAddKw() { const v = addKw.value.trim(); if (v && !addForm.keywords.includes(v)) { addForm.keywords.push(v); addKw.value = '' } }
async function submitAdd() {
  if (!addRef.value) return
  try { await addRef.value.validate() } catch { return }
  try {
    await createKnowledge(addForm)
    ElMessage.success('添加成功'); addVisible.value = false; loadList(); loadIndexStatus(); loadCategories()
  } catch (e: any) { ElMessage.error(e.response?.data?.detail || '添加失败') }
}

// ── 详情编辑 ──
const form = reactive({ question: '', answer: '', keywords: [] as string[], category: '通用' })
const editMode = ref(false)
const formKw = ref('')
function pushFormKw() { const v = formKw.value.trim(); if (v && !form.keywords.includes(v)) { form.keywords.push(v); formKw.value = '' } }
async function saveEdit() {
  if (!selected.value) return
  try {
    await updateKnowledge(selected.value.id, { question: form.question, answer: form.answer, keywords: form.keywords, category: form.category })
    ElMessage.success('已保存'); editMode.value = false
    const idx = list.value.findIndex(i => i.id === selected.value!.id)
    if (idx !== -1) { list.value[idx] = { ...list.value[idx], ...form }; selected.value = { ...list.value[idx] } }
    loadIndexStatus(); loadCategories()
  } catch (e: any) { ElMessage.error(e.response?.data?.detail || '保存失败') }
}
function cancelEdit() { editMode.value = false; if (selected.value) selectItem(selected.value) }

// ── 导入导出 ──
const importVisible = ref(false); const importFile = ref<File | null>(null); const importLoading = ref(false)
function onFileChange(f: any) { importFile.value = f.raw }
async function doImport() {
  if (!importFile.value) { ElMessage.warning('请选择文件'); return }
  importLoading.value = true
  try {
    const data = JSON.parse(await importFile.value.text())
    if (!Array.isArray(data)) { ElMessage.error('格式错误'); return }
    await importKnowledge(data); ElMessage.success('导入成功'); importVisible.value = false; loadList(); loadIndexStatus(); loadCategories()
  } catch (e: any) { ElMessage.error(e.response?.data?.detail || '导入失败') }
  finally { importLoading.value = false }
}
async function doExport() {
  try {
    const res = await exportKnowledge()
    const data = Array.isArray(res.data) ? res.data : (res.data as any)?.items || []
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob)
    a.download = `knowledge_${new Date().toISOString().split('T')[0]}.json`; a.click(); URL.revokeObjectURL(a.href)
    ElMessage.success('导出成功')
  } catch (e: any) { ElMessage.error(e.response?.data?.detail || '导出失败') }
}

// ── RAG 配置 ──
const indexStatus = ref<IndexStatus | null>(null)
const rebuildLoading = ref(false)
const ragForm = reactive({ chunk_size: 500, chunk_overlap: 50 })
const embeddingModel = ref('')
const ragSaving = ref(false)

// 重建进度
const rebuildActive = ref(false)
const rebuildTotal = ref(0)
const rebuildCurrent = ref(0)
const rebuildSuccessCount = ref(0)
const rebuildFailCount = ref(0)
const rebuildDone = ref(false)

async function loadIndexStatus() { try { indexStatus.value = (await getIndexStatus()).data } catch { /* */ } }
async function loadRAGConfig() {
  try {
    const d = (await getSettings()).data as any
    if (d.rag) { ragForm.chunk_size = d.rag.chunk_size ?? 500; ragForm.chunk_overlap = d.rag.chunk_overlap ?? 50 }
    if (d.embedding) embeddingModel.value = d.embedding.model || ''
  } catch { /* */ }
}
async function saveRAG() {
  ragSaving.value = true
  try { await updateSettings({ rag: { ...ragForm } } as any); ElMessage.success('RAG 配置已保存') }
  catch (e: any) { ElMessage.error(e.response?.data?.detail || '保存失败') }
  finally { ragSaving.value = false }
}
async function doRebuild() {
  try {
    await ElMessageBox.confirm('重建索引可能需要一些时间，确定继续？', '确认', { type: 'warning' })
  } catch { return }

  rebuildLoading.value = true
  rebuildActive.value = true
  rebuildDone.value = false
  rebuildTotal.value = 0
  rebuildCurrent.value = 0
  rebuildSuccessCount.value = 0
  rebuildFailCount.value = 0

  try {
    const reader = await rebuildIndexSSE()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const evt = JSON.parse(line.slice(6))
          if (evt.type === 'start') {
            rebuildTotal.value = evt.total
          } else if (evt.type === 'progress') {
            rebuildCurrent.value = evt.current
          } else if (evt.type === 'done') {
            rebuildDone.value = true
            rebuildSuccessCount.value = evt.success_count
            rebuildFailCount.value = evt.fail_count
          } else if (evt.type === 'error') {
            ElMessage.error(evt.message)
            rebuildDone.value = true
          }
        } catch { /* skip */ }
      }
    }

    if (rebuildFailCount.value > 0) {
      ElMessage.warning(`重建完成，成功 ${rebuildSuccessCount.value} 条，失败 ${rebuildFailCount.value} 条`)
    } else {
      ElMessage.success(`索引重建成功，共 ${rebuildSuccessCount.value} 条`)
    }
    loadIndexStatus()
  } catch (e: any) {
    ElMessage.error(e.message || '重建失败')
    rebuildDone.value = true
  } finally {
    rebuildLoading.value = false
  }
}

onMounted(() => { loadCategories(); loadList(); loadIndexStatus(); loadRAGConfig() })
</script>

<template>
  <div class="three-col">
    <!-- ====== 左栏：分类 ====== -->
    <aside class="col col-left">
      <div class="col-header"><span class="col-title">分类</span></div>
      <nav class="cat-nav">
        <div
          v-for="cat in categories" :key="cat"
          class="cat-item" :class="{ active: activeCategory === cat }"
        >
          <!-- 编辑态 -->
          <template v-if="editingCat === cat && cat !== '全部'">
            <el-input v-model="editingCatValue" size="small" style="flex:1" @keyup.enter="confirmEditCat(cat)" />
            <el-button :icon="Edit" link size="small" @click="confirmEditCat(cat)" />
            <el-button :icon="Close" link size="small" @click="editingCat = null" />
          </template>
          <!-- 正常态 -->
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
      <!-- 添加分类 -->
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
        <el-input v-model="keyword" placeholder="搜索问题或答案…" clearable @keyup.enter="handleSearch" @clear="handleSearch">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-button type="primary" :icon="Plus" @click="openAdd">添加</el-button>
        <el-button v-if="activeCategory !== '全部'" type="danger" :icon="Delete" @click="handleDeleteAllInCategory">删除全部</el-button>
      </div>
      <div v-loading="loading" class="item-list">
        <div v-for="item in list" :key="item.id" class="item-card" :class="{ active: selected?.id === item.id }" @click="selectItem(item)">
          <div class="item-top">
            <span class="item-id">{{ item.id }}</span>
            <el-tag size="small" effect="plain">{{ item.category }}</el-tag>
          </div>
          <p class="item-q">{{ item.question }}</p>
          <div class="item-bottom">
            <div class="item-kws">
              <el-tag v-for="kw in (item.keywords||[]).slice(0,2)" :key="kw" size="small" type="info" round>{{ kw }}</el-tag>
              <span v-if="(item.keywords||[]).length > 2" class="more-kw">+{{ item.keywords.length - 2 }}</span>
            </div>
            <el-button :icon="Delete" type="danger" text size="small" @click="handleDelete(item, $event)" />
          </div>
        </div>
        <el-empty v-if="!loading && list.length === 0" description="暂无数据" :image-size="64" />
      </div>
      <div class="col-footer center">
        <el-pagination v-model:current-page="currentPage" :page-size="pageSize" :total="total" small background layout="prev, pager, next" @current-change="handlePageChange" />
      </div>
    </section>

    <!-- ====== 右栏：可滚动详情 + 固定底部 RAG 配置 ====== -->
    <aside class="col col-right">
      <!-- 知识详情区域（选中时显示） -->
      <template v-if="selected">
        <div class="col-header"><span class="col-title">知识详情 — {{ selected.id }}</span></div>

        <!-- 可滚动区域：详情内容 + 编辑表单 -->
        <div class="detail-scroll">
          <el-card shadow="never" class="detail-block">
            <p class="meta-line"><span class="meta-label">ID</span>{{ selected.id }}</p>
            <p class="meta-line"><span class="meta-label">分类</span><el-tag size="small" effect="plain">{{ selected.category }}</el-tag></p>
            <p class="meta-line"><span class="meta-label">关键词</span>
              <template v-if="(selected.keywords||[]).length"><el-tag v-for="kw in selected.keywords" :key="kw" size="small" type="info" round style="margin-right:4px">{{ kw }}</el-tag></template>
              <span v-else class="text-muted">无</span>
            </p>
          </el-card>
          <el-card shadow="never" class="detail-block">
            <template #header><span class="block-title">❓ 问题</span></template>
            <el-input v-if="editMode" v-model="form.question" type="textarea" :rows="2" />
            <p v-else class="block-text">{{ selected.question }}</p>
          </el-card>
          <el-card shadow="never" class="detail-block">
            <template #header><span class="block-title">💬 答案</span></template>
            <el-input v-if="editMode" v-model="form.answer" type="textarea" :rows="5" />
            <p v-else class="block-text pre">{{ selected.answer }}</p>
          </el-card>
          <template v-if="editMode">
            <el-card shadow="never" class="detail-block">
              <template #header><span class="block-title">编辑属性</span></template>
              <div class="field-row"><span class="field-label">分类</span>
                <el-select v-model="form.category" size="small" style="flex:1">
                  <el-option v-for="c in categories.filter(c=>c!=='全部')" :key="c" :label="c" :value="c" />
                </el-select>
              </div>
              <div class="field-row" style="margin-top:10px;align-items:flex-start"><span class="field-label">关键词</span>
                <div style="flex:1">
                  <div style="display:flex;gap:6px;margin-bottom:6px"><el-input v-model="formKw" size="small" placeholder="回车添加" @keyup.enter="pushFormKw" /><el-button size="small" @click="pushFormKw">添加</el-button></div>
                  <div style="display:flex;flex-wrap:wrap;gap:4px"><el-tag v-for="(kw,i) in form.keywords" :key="kw" closable size="small" @close="form.keywords.splice(i,1)">{{ kw }}</el-tag></div>
                </div>
              </div>
            </el-card>
          </template>

        </div>
      </template>
      <div v-else class="empty-detail"><el-empty description="选择一条知识查看详情" :image-size="64" /></div>

      <!-- 固定底部：编辑按钮 + RAG 配置 -->
      <div class="right-fixed-bottom">
        <!-- 编辑/保存按钮（仅选中时显示） -->
        <template v-if="selected">
          <div v-if="editMode" class="action-bar" style="margin-bottom:12px">
            <el-button type="primary" style="flex:1" @click="saveEdit">保存</el-button>
            <el-button style="flex:1" @click="cancelEdit">取消</el-button>
          </div>
          <el-button v-else type="primary" :icon="Edit" class="full-btn" style="margin-bottom:12px" @click="editMode = true">编辑知识</el-button>
        </template>

        <el-divider style="margin:0 0 12px" />

        <!-- 重建索引进度 -->
        <div v-if="rebuildActive" class="rebuild-progress">
          <div class="rebuild-progress-header">
            <span class="rebuild-progress-title">🔄 重建向量索引</span>
            <span v-if="rebuildDone" class="rebuild-progress-close" @click="rebuildActive = false">✕</span>
          </div>
          <el-progress :percentage="rebuildTotal ? Math.round(rebuildCurrent / rebuildTotal * 100) : 0" :status="rebuildDone ? (rebuildFailCount > 0 ? 'warning' : 'success') : undefined" :stroke-width="14" />
          <div class="rebuild-progress-stats">
            <span v-if="!rebuildDone">{{ rebuildCurrent }} / {{ rebuildTotal }}</span>
            <span v-else>成功 {{ rebuildSuccessCount }}<template v-if="rebuildFailCount"> · 失败 {{ rebuildFailCount }}</template></span>
          </div>
        </div>

        <div class="rag-section">
          <div class="col-title" style="margin-bottom:14px"><el-icon><Setting /></el-icon> RAG 配置</div>
          <div class="rag-field-row"><span class="rag-field-label">Chunk 大小</span><el-input-number v-model="ragForm.chunk_size" :min="100" :max="5000" :step="100" size="small" /></div>
          <div class="rag-field-row"><span class="rag-field-label">重叠大小</span><el-input-number v-model="ragForm.chunk_overlap" :min="0" :max="1000" :step="10" size="small" /></div>
          <div class="rag-field-row"><span class="rag-field-label">Embedding</span><span class="rag-field-value">{{ embeddingModel || '未配置' }}</span></div>
          <div class="rag-btn-group">
            <el-button type="primary" :loading="ragSaving" @click="saveRAG">保存 RAG 配置</el-button>
            <el-button :icon="Refresh" :loading="rebuildLoading" @click="doRebuild">重建向量索引</el-button>
          </div>
          <p v-if="indexStatus" class="index-info">📊 {{ indexStatus.count }} 条向量 · 维度 {{ indexStatus.dimension }}</p>
        </div>
      </div>
    </aside>

    <!-- 添加对话框 -->
    <el-dialog v-model="addVisible" title="添加知识" width="560px" destroy-on-close>
      <el-form ref="addRef" :model="addForm" :rules="addRules" label-width="70px">
        <el-form-item label="问题" prop="question"><el-input v-model="addForm.question" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="答案" prop="answer"><el-input v-model="addForm.answer" type="textarea" :rows="4" /></el-form-item>
        <el-form-item label="分类" prop="category">
          <el-select v-model="addForm.category"><el-option v-for="c in categories.filter(c=>c!=='全部')" :key="c" :label="c" :value="c" /></el-select>
        </el-form-item>
        <el-form-item label="关键词">
          <div style="display:flex;gap:8px;margin-bottom:6px"><el-input v-model="addKw" placeholder="回车添加" style="width:180px" @keyup.enter="pushAddKw" /><el-button @click="pushAddKw">添加</el-button></div>
          <div style="display:flex;flex-wrap:wrap;gap:4px"><el-tag v-for="(kw,i) in addForm.keywords" :key="kw" closable @close="addForm.keywords.splice(i,1)">{{ kw }}</el-tag></div>
        </el-form-item>
      </el-form>
      <template #footer><el-button @click="addVisible = false">取消</el-button><el-button type="primary" @click="submitAdd">确定</el-button></template>
    </el-dialog>

    <!-- 导入对话框 -->
    <el-dialog v-model="importVisible" title="导入知识库" width="480px">
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

/* 分类 */
.cat-nav { flex: 1; overflow-y: auto; padding: 4px 0; }
.cat-item { display: flex; align-items: center; gap: 4px; padding: 6px 12px; font-size: 13px; color: var(--el-text-color-regular); transition: background .15s; }
.cat-item:hover { background: var(--el-fill-color-light); }
.cat-item:hover .cat-ops { opacity: 1; }
.cat-item.active { color: var(--el-color-primary); background: var(--el-color-primary-light-9); }
.cat-item.active .cat-label { font-weight: 500; }
.cat-label { display: flex; align-items: center; gap: 8px; flex: 1; cursor: pointer; padding: 2px 0; }
.cat-ops { display: flex; gap: 0; opacity: 0; transition: opacity .15s; flex-shrink: 0; }
.cat-add { padding: 8px 12px; border-top: 1px solid var(--el-border-color-lighter); display: flex; gap: 6px; flex-wrap: wrap; }

/* 列表 */
.item-list { flex: 1; overflow-y: auto; padding: 10px 12px; }
.item-card { padding: 10px 14px; border-radius: 8px; margin-bottom: 6px; cursor: pointer; border: 1px solid transparent; transition: all .15s; }
.item-card:hover { background: var(--el-fill-color-light); }
.item-card.active { background: var(--el-color-primary-light-9); border-color: var(--el-color-primary-light-5); }
.item-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.item-id { font-size: 11px; color: var(--el-text-color-placeholder); font-family: monospace; }
.item-q { font-size: 13px; color: var(--el-text-color-primary); line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; margin: 0 0 6px; }
.item-bottom { display: flex; justify-content: space-between; align-items: center; }
.item-kws { display: flex; align-items: center; gap: 4px; }
.more-kw { font-size: 11px; color: var(--el-text-color-secondary); }

/* 右栏 */
.detail-scroll { flex: 1; overflow-y: auto; padding: 12px 16px; }
.empty-detail { flex: 1; display: flex; align-items: center; justify-content: center; }

.right-fixed-bottom { flex-shrink: 0; padding: 12px 16px; border-top: 1px solid var(--el-border-color-lighter); max-height: 50%; overflow-y: auto; }

.detail-block { margin-bottom: 12px; }
.detail-block :deep(.el-card__header) { padding: 10px 14px; font-size: 13px; }
.detail-block :deep(.el-card__body) { padding: 12px 14px; }
.meta-line { margin: 0 0 6px; font-size: 13px; color: var(--el-text-color-regular); display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.meta-label { font-weight: 600; min-width: 48px; color: var(--el-text-color-primary); }
.block-title { font-size: 13px; font-weight: 600; }
.block-text { margin: 0; font-size: 13px; line-height: 1.65; color: var(--el-text-color-primary); }
.block-text.pre { white-space: pre-wrap; }
.text-muted { color: var(--el-text-color-placeholder); font-size: 13px; }

.field-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.field-label { font-size: 13px; color: var(--el-text-color-regular); min-width: 72px; white-space: nowrap; }
.action-bar { display: flex; gap: 8px; }
.full-btn { width: 100%; }

.rag-section {}
.rag-btn-group { display: flex; flex-direction: column; gap: 8px; margin-top: 12px; }
.rag-btn-group .el-button { width: 100%; margin-left: 0; }
.rag-field-row { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
.rag-field-label { font-size: 14px; color: var(--el-text-color-regular); min-width: 80px; white-space: nowrap; line-height: 1.8; }
.rag-field-value { font-size: 14px; color: var(--el-text-color-placeholder); line-height: 1.8; }
.index-info { margin: 8px 0 0; font-size: 12px; color: var(--el-text-color-secondary); text-align: center; }

/* 重建索引进度 */
.rebuild-progress { margin-bottom: 14px; padding: 10px 12px; background: var(--el-fill-color-lighter); border-radius: 8px; }
.rebuild-progress-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.rebuild-progress-title { font-size: 13px; font-weight: 600; }
.rebuild-progress-close { cursor: pointer; color: var(--el-text-color-placeholder); font-size: 14px; }
.rebuild-progress-close:hover { color: var(--el-text-color-primary); }
.rebuild-progress-stats { margin-top: 6px; font-size: 12px; color: var(--el-text-color-secondary); text-align: center; }
</style>
