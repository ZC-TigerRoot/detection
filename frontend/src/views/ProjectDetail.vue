<template>
  <div class="detail-page" v-loading="loading" element-loading-text="加载中…">
    <!-- ===== 顶栏 ===== -->
    <div class="topbar">
      <div class="topbar-left">
        <el-button text class="back-btn" @click="$router.push('/')">
          <el-icon><ArrowLeft /></el-icon> 返回
        </el-button>
        <div class="project-meta">
          <span class="project-name">{{ project?.name || '未命名项目' }}</span>
          <el-tag v-if="project" size="small" class="type-tag" :class="project.project_type">
            {{ project.project_type === 'basic' ? '基础/单次' : '年度' }}
          </el-tag>
          <el-tag v-if="project" size="small" :type="statusType(project.status)">
            {{ statusLabel(project.status) }}
          </el-tag>
        </div>
      </div>
      <div class="topbar-actions">
        <el-upload
          :show-file-list="false"
          :http-request="onUpload"
          :disabled="uploading"
          multiple
          accept=".docx,.doc,.xlsx,.xls,.pdf,.png,.jpg,.jpeg,.txt"
        >
          <el-button :loading="uploading" :icon="uploading ? undefined : Upload">
            {{ uploading ? '上传中…' : '上传方案' }}
          </el-button>
        </el-upload>
        <el-button
          type="warning"
          :disabled="!project?.files?.length || uploading"
          :icon="MagicStick"
          @click="openParseDialog"
        >
          AI 解析
        </el-button>
        <el-button :loading="detecting" :disabled="!project?.files?.length" @click="onDetectType" :icon="Monitor">
          识别类型
        </el-button>
        <el-divider direction="vertical" />
        <el-button type="success" :loading="saving" :icon="DocumentChecked" @click="onSave(false)">
          保存校对
        </el-button>
        <el-button type="primary" :loading="exporting" :icon="Download" @click="onExport">
          导出 Word
        </el-button>
      </div>
    </div>

    <!-- ===== 提示条 ===== -->
    <transition name="slide-down">
      <el-alert
        v-if="allFilesNoText"
        type="warning"
        title="所有附件均未提取到文本，AI 解析将无法进行；请上传带文字层的 docx/pdf 等方案文件"
        show-icon
        :closable="false"
        class="global-alert"
      />
    </transition>
    <transition name="slide-down">
      <el-alert
        v-if="project?.parse_error"
        type="error"
        :title="'解析错误: ' + project.parse_error"
        show-icon
        :closable="false"
        class="global-alert"
      />
    </transition>

    <!-- ===== 主内容区 ===== -->
    <div class="main-grid">
      <!-- 左列 -->
      <div class="left-col">
        <!-- 基本信息卡片 -->
        <div class="card">
          <div class="card-title">
            <el-icon><InfoFilled /></el-icon> 基本信息
          </div>
          <el-form v-if="form" label-width="80px" size="default" class="info-form">
            <el-form-item label="项目名称">
              <el-input v-model="form.name" placeholder="未填写" />
            </el-form-item>
            <el-form-item label="委托单位">
              <el-input v-model="form.client_name" placeholder="未填写" />
            </el-form-item>
            <el-form-item label="地址">
              <el-input v-model="form.address" placeholder="未填写" />
            </el-form-item>
            <el-form-item label="联系人">
              <el-input v-model="form.contact" placeholder="未填写" />
            </el-form-item>
            <el-form-item label="电话">
              <el-input v-model="form.phone" placeholder="未填写" />
            </el-form-item>
            <el-form-item label="类型">
              <div class="type-row">
                <el-tag
                  :type="form.project_type === 'basic' ? 'warning' : 'success'"
                  size="large"
                  effect="plain"
                >
                  {{ form.project_type === 'basic' ? '基础/单次' : '年度' }}
                </el-tag>
                <span class="type-hint">上传后自动识别</span>
              </div>
            </el-form-item>
            <el-form-item label="年份">
              <el-input v-model="form.year" placeholder="如 2026" />
            </el-form-item>
            <div class="coord-row">
              <el-form-item label="经度" class="coord-item">
                <el-input v-model="form.longitude" placeholder="0.000000" />
              </el-form-item>
              <el-form-item label="纬度" class="coord-item">
                <el-input v-model="form.latitude" placeholder="0.000000" />
              </el-form-item>
            </div>
            <el-form-item label="概况">
              <el-input v-model="form.overview" type="textarea" :rows="3" placeholder="项目概况摘要" />
            </el-form-item>
            <el-form-item label="备注">
              <el-input v-model="form.remark" type="textarea" :rows="2" />
            </el-form-item>
            <div class="form-footer">
              <el-button type="primary" plain size="small" @click="onSaveMeta">保存基本信息</el-button>
            </div>
          </el-form>
        </div>

        <!-- 附件卡片 -->
        <div class="card">
          <div class="card-title">
            <el-icon><Files /></el-icon> 附件
            <span v-if="extractSummary" class="card-badge">{{ extractSummary }}</span>
          </div>
          <el-empty v-if="!project?.files?.length" description="尚未上传附件" :image-size="56" />
          <ul v-else class="file-list">
            <li v-for="f in project.files" :key="f.id" class="file-item">
              <el-icon class="file-icon"><Document /></el-icon>
              <span class="file-name" :title="f.original_name">{{ f.original_name }}</span>
              <el-tag size="small" :type="f.has_text ? 'success' : 'info'" effect="plain">{{ f.file_ext }}</el-tag>
              <el-tooltip :content="extTooltip(f)" placement="top">
                <el-tag size="small" :type="extStatusType(f)" effect="plain">{{ extStatusLabel(f) }}</el-tag>
              </el-tooltip>
              <el-button link type="primary" size="small" @click="previewFile(f)">原文</el-button>
            </li>
          </ul>
        </div>

        <!-- 导出历史卡片 -->
        <div class="card">
          <div class="card-title">
            <el-icon><Download /></el-icon> 导出历史
          </div>
          <el-empty v-if="!project?.exports?.length" description="暂无导出记录" :image-size="48" />
          <ul v-else class="file-list">
            <li v-for="e in project.exports" :key="e.id" class="file-item">
              <el-icon class="file-icon"><Document /></el-icon>
              <span class="file-name">{{ e.file_name }}</span>
              <el-button link type="primary" size="small" @click="downloadExport(e.id, e.file_name)">
                下载
              </el-button>
            </li>
          </ul>
        </div>
      </div>

      <!-- 右列 -->
      <div class="right-col">
        <div class="card card-table">
          <div class="table-toolbar">
            <div class="card-title" style="margin-bottom: 0">
              <el-icon><Grid /></el-icon> 监测条目
              <span v-if="items.length" class="card-badge">{{ items.length }} 条</span>
            </div>
            <div class="table-actions">
              <el-button size="small" :icon="Plus" @click="addRow">新增行</el-button>
              <el-button size="small" type="danger" plain :icon="Delete" :disabled="!selected.length" @click="removeSelected">
                删除选中
              </el-button>
            </div>
          </div>

          <el-empty
            v-if="!items.length"
            description="暂无监测条目，请先上传方案后点击「AI 解析」"
            :image-size="80"
          />
          <el-table
            v-else
            :data="items"
            border
            size="small"
            :height="tableHeight"
            class="items-table"
            @selection-change="(v) => (selected = v)"
          >
            <el-table-column type="selection" width="38" />
            <el-table-column label="类别" min-width="110">
              <template #default="{ row }">
                <el-input v-model="row.category" size="small" />
              </template>
            </el-table-column>
            <el-table-column label="编号" width="96">
              <template #default="{ row }">
                <el-input v-model="row.outlet_code" size="small" />
              </template>
            </el-table-column>
            <el-table-column label="名称/点位" min-width="130">
              <template #default="{ row }">
                <el-input v-model="row.outlet_name" size="small" />
              </template>
            </el-table-column>
            <el-table-column label="位置" min-width="110">
              <template #default="{ row }">
                <el-input v-model="row.point_location" size="small" />
              </template>
            </el-table-column>
            <el-table-column label="监测因子" min-width="180">
              <template #default="{ row }">
                <el-input v-model="row.factors" size="small" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" />
              </template>
            </el-table-column>
            <el-table-column label="采样频次" min-width="120">
              <template #default="{ row }">
                <el-input v-model="row.sample_freq" size="small" />
              </template>
            </el-table-column>
            <el-table-column label="周期频次" width="100">
              <template #default="{ row }">
                <el-input v-model="row.period_freq" size="small" />
              </template>
            </el-table-column>
            <el-table-column label="年次数" width="88">
              <template #default="{ row }">
                <el-input v-model="row.annual_times" size="small" />
              </template>
            </el-table-column>
            <el-table-column label="备注" min-width="100">
              <template #default="{ row }">
                <el-input v-model="row.remark" size="small" />
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>
    </div>

    <!-- ===== 抽取原文抽屉 ===== -->
    <el-drawer v-model="textVisible" title="附件原文" size="46%">
      <pre class="raw-text">{{ previewText }}</pre>
    </el-drawer>

    <!-- ===== AI 解析进度对话框 ===== -->
    <ParseProgressDialog
      v-model="parseDialogVisible"
      :project-id="props.id"
      @done="onParseDone"
      @failed="onParseFailed"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  ArrowLeft,
  Delete,
  Document,
  DocumentChecked,
  Download,
  Files,
  Grid,
  InfoFilled,
  MagicStick,
  Monitor,
  Plus,
  Upload,
} from '@element-plus/icons-vue'
import {
  detectType,
  downloadExport,
  exportProject,
  getFileText,
  getProject,
  saveItems,
  updateProject,
  uploadFiles,
} from '../api'
import ParseProgressDialog from '../components/ParseProgressDialog.vue'

const props = defineProps({ id: { type: [String, Number], required: true } })

const loading = ref(false)
const uploadingCount = ref(0)
const uploading = computed(() => uploadingCount.value > 0)
const detecting = ref(false)
const saving = ref(false)
const exporting = ref(false)
const project = ref(null)
const form = ref(null)
const items = ref([])
const selected = ref([])
const textVisible = ref(false)
const previewText = ref('')
const parseDialogVisible = ref(false)

const tableHeight = 580

function statusLabel(s) {
  return { draft: '草稿', reviewing: '校对中', confirmed: '已确认', exported: '已导出', parse_failed: '解析失败' }[s] || s
}
function statusType(s) {
  return { draft: 'info', reviewing: 'warning', confirmed: 'success', exported: 'success', parse_failed: 'danger' }[s] || ''
}

const extractSummary = computed(() => {
  const files = project.value?.files || []
  if (!files.length) return ''
  const ok = files.filter((f) => f.extract_status === 'success').length
  return `${ok}/${files.length}`
})

const allFilesNoText = computed(() => {
  const files = project.value?.files || []
  return files.length > 0 && files.every((f) => f.extract_status !== 'success')
})

function extStatusLabel(f) {
  return { success: '已提取', no_text: '无文本', failed: '提取失败' }[f.extract_status] || '未知'
}
function extStatusType(f) {
  return { success: 'success', no_text: 'warning', failed: 'danger' }[f.extract_status] || 'info'
}
function extTooltip(f) {
  const err = f.extract_error ? `：${f.extract_error}` : ''
  return `${extStatusLabel(f)}${err}`
}

function emptyRow() {
  return {
    category: '', outlet_code: '', outlet_name: '', point_location: '',
    factors: '', sample_freq: '', period_freq: '', monitor_days: '',
    samples_per_day: '', annual_times: '', months_plan: '', standard_text: '',
    remark: '', sort_order: items.value.length,
  }
}

async function load() {
  loading.value = true
  try {
    const { data } = await getProject(props.id)
    project.value = data
    form.value = {
      name: data.name, client_name: data.client_name, address: data.address,
      contact: data.contact, phone: data.phone, project_type: data.project_type,
      year: data.year || '', longitude: data.longitude, latitude: data.latitude,
      overview: data.overview, remark: data.remark,
    }
    items.value = (data.items || []).map((i) => ({ ...i }))
  } finally {
    loading.value = false
  }
}

async function onUpload({ file }) {
  if (uploadingCount.value > 0) {
    ElMessage.warning('请等待当前上传完成后再上传新文件')
    return
  }
  uploadingCount.value++
  try {
    const { data } = await uploadFiles(props.id, [file])
    project.value = data
    form.value.project_type = data.project_type
    const label = data.project_type === 'basic' ? '基础/单次' : '年度'
    const f = (data.files || []).find((x) => x.original_name === file.name)
    if (f && f.extract_status === 'success') {
      ElMessage.success(`已上传 ${file.name}，识别类型：${label}，文本提取完成`)
    } else if (f && f.extract_status === 'failed') {
      ElMessage.warning(`已上传 ${file.name}，但文本提取失败：${f.extract_error}`)
    } else if (f) {
      ElMessage.warning(`已上传 ${file.name}，但未提取到文本，无法进行 AI 解析`)
    } else {
      ElMessage.success(`已上传 ${file.name}，识别类型：${label}`)
    }
  } finally {
    uploadingCount.value--
  }
}

function openParseDialog() {
  parseDialogVisible.value = true
}

async function onParseDone() {
  await load()
  ElMessage.success(`解析完成，请核对右侧表格`)
}

function onParseFailed(msg) {
  ElMessage.error(`解析失败：${msg}`)
}

async function onDetectType() {
  detecting.value = true
  try {
    const { data } = await detectType(props.id)
    form.value.project_type = data.project_type
    const res = await updateProject(props.id, { ...form.value })
    project.value = res.data
    const label = data.project_type === 'basic' ? '基础/单次' : '年度'
    ElMessage.success(`已识别并应用类型：${label}（${data.reason}）`)
  } finally {
    detecting.value = false
  }
}

async function onSaveMeta() {
  const { data } = await updateProject(props.id, { ...form.value })
  project.value = data
  ElMessage.success('基本信息已保存')
}

async function onSave(confirmed = true) {
  saving.value = true
  try {
    await updateProject(props.id, { ...form.value })
    const { data } = await saveItems(props.id, {
      items: items.value.map((it, idx) => ({ ...it, sort_order: idx })),
      status: confirmed ? 'confirmed' : 'reviewing',
    })
    project.value = data
    items.value = (data.items || []).map((i) => ({ ...i }))
    ElMessage.success('已保存')
  } finally {
    saving.value = false
  }
}

async function onExport() {
  exporting.value = true
  try {
    await onSave(true)
    const { data } = await exportProject(props.id, { export_type: form.value.project_type })
    ElMessage.success('导出成功')
    downloadExport(data.id, data.file_name)
    await load()
  } finally {
    exporting.value = false
  }
}

function addRow() {
  items.value.push(emptyRow())
}
function removeSelected() {
  const set = new Set(selected.value)
  items.value = items.value.filter((r) => !set.has(r))
  selected.value = []
}

async function previewFile(f) {
  const { data } = await getFileText(props.id, f.id)
  previewText.value = data.text || '(空)'
  textVisible.value = true
}

watch(() => props.id, () => load(), { immediate: false })
onMounted(load)
</script>

<style scoped>
/* ===== 页面布局 ===== */
.detail-page {
  display: flex;
  flex-direction: column;
  min-height: 100%;
  background: #f0f2f5;
}

/* ===== 顶栏 ===== */
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 24px;
  background: #fff;
  border-bottom: 1px solid #e5e7eb;
  flex-wrap: wrap;
  position: sticky;
  top: 0;
  z-index: 100;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}
.topbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.back-btn {
  color: #606266;
  flex: none;
}
.project-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.project-name {
  font-size: 16px;
  font-weight: 600;
  color: #111827;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 320px;
}
.type-tag.basic {
  --el-tag-bg-color: #fef3c7;
  --el-tag-border-color: #fcd34d;
  --el-tag-text-color: #92400e;
}
.type-tag.annual {
  --el-tag-bg-color: #d1fae5;
  --el-tag-border-color: #6ee7b7;
  --el-tag-text-color: #065f46;
}
.topbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  flex: none;
}

/* ===== 提示条 ===== */
.global-alert {
  margin: 8px 24px 0;
}
.slide-down-enter-active,
.slide-down-leave-active {
  transition: all 0.28s ease;
}
.slide-down-enter-from,
.slide-down-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

/* ===== 主网格 ===== */
.main-grid {
  display: grid;
  grid-template-columns: 300px 1fr;
  gap: 16px;
  padding: 16px 24px 32px;
  align-items: start;
}

/* ===== 卡片 ===== */
.card {
  background: #fff;
  border-radius: 10px;
  border: 1px solid #e5e7eb;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
  overflow: hidden;
}
.left-col {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.right-col {
  min-width: 0;
}
.card-title {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 14px 16px 10px;
  font-size: 14px;
  font-weight: 600;
  color: #374151;
  border-bottom: 1px solid #f3f4f6;
  margin-bottom: 0;
}
.card-badge {
  margin-left: auto;
  font-size: 11px;
  font-weight: normal;
  color: #9ca3af;
  background: #f3f4f6;
  border-radius: 10px;
  padding: 1px 7px;
}

/* ===== 信息表单 ===== */
.info-form {
  padding: 12px 16px 8px;
}
.type-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.type-hint {
  font-size: 12px;
  color: #9ca3af;
}
.coord-row {
  display: flex;
  gap: 8px;
}
.coord-item {
  flex: 1;
  min-width: 0;
}
.coord-item :deep(.el-form-item__label) {
  font-size: 12px;
}
.form-footer {
  padding: 0 0 10px;
  text-align: right;
}

/* ===== 文件列表 ===== */
.file-list {
  list-style: none;
  padding: 8px 16px;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.file-item {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 6px 8px;
  border-radius: 6px;
  font-size: 13px;
  transition: background 0.15s;
}
.file-item:hover {
  background: #f9fafb;
}
.file-icon {
  color: #9ca3af;
  flex: none;
}
.file-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #374151;
}

/* ===== 监测条目区 ===== */
.card-table {
  display: flex;
  flex-direction: column;
}
.table-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px 10px;
  border-bottom: 1px solid #f3f4f6;
}
.table-actions {
  display: flex;
  gap: 8px;
  flex: none;
}
.items-table {
  border: none !important;
  border-top: 1px solid #f3f4f6 !important;
}
.items-table :deep(th.el-table__cell) {
  background: #f9fafb;
  color: #6b7280;
  font-weight: 500;
}
.items-table :deep(td.el-table__cell) {
  padding: 4px 0;
}

/* ===== 原文抽屉 ===== */
.raw-text {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  line-height: 1.65;
  margin: 0;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  color: #374151;
}
</style>
