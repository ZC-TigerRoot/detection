<template>
  <div class="page" v-loading="loading">
    <div class="page-header">
      <div>
        <el-button text @click="$router.push('/')">← 返回</el-button>
        <h1 class="page-title" style="display: inline; margin-left: 8px">
          {{ project?.name || '未命名项目' }}
          <el-tag v-if="project" size="small" style="margin-left: 8px">{{
            project.project_type === 'basic' ? '基础/单次' : '年度'
          }}</el-tag>
          <el-tag v-if="project" size="small" :type="statusType(project.status)" style="margin-left: 6px">
            {{ statusLabel(project.status) }}
          </el-tag>
        </h1>
      </div>
      <div class="actions">
        <el-upload :show-file-list="false" :http-request="onUpload" multiple accept=".docx,.doc,.xlsx,.xls,.pdf,.png,.jpg,.jpeg,.txt">
          <el-button :loading="uploading">
            {{ uploading ? '上传并提取中…' : '上传方案' }}
          </el-button>
        </el-upload>
        <el-button type="warning" :loading="parsing" :disabled="!project?.files?.length" @click="onParse">
          AI 解析
        </el-button>
        <el-button :loading="detecting" :disabled="!project?.files?.length" @click="onDetectType">
          识别类型
        </el-button>
        <el-button type="success" :loading="saving" @click="onSave(false)">保存校对</el-button>
        <el-button type="primary" :loading="exporting" @click="onExport">导出 Word</el-button>
      </div>
    </div>

    <el-alert
      v-if="allFilesNoText"
      type="warning"
      title="所有附件均未提取到文本，AI 解析将无法进行；请上传带文字层的 docx/pdf 等方案文件"
      show-icon
      style="margin-bottom: 12px"
    />

    <el-alert
      v-if="project?.parse_error"
      type="error"
      :title="'解析错误: ' + project.parse_error"
      show-icon
      style="margin-bottom: 12px"
    />

    <el-row :gutter="12">
      <el-col :span="8">
        <div class="card">
          <h3 class="sec">基本信息</h3>
          <el-form label-width="88px" size="default" v-if="form">
            <el-form-item label="项目名称">
              <el-input v-model="form.name" />
            </el-form-item>
            <el-form-item label="客户">
              <el-input v-model="form.client_name" />
            </el-form-item>
            <el-form-item label="地址">
              <el-input v-model="form.address" />
            </el-form-item>
            <el-form-item label="联系人">
              <el-input v-model="form.contact" />
            </el-form-item>
            <el-form-item label="电话">
              <el-input v-model="form.phone" />
            </el-form-item>
            <el-form-item label="类型">
              <el-tag :type="form.project_type === 'basic' ? 'warning' : 'success'" size="large">
                {{ form.project_type === 'basic' ? '基础/单次' : '年度' }}
              </el-tag>
              <span style="margin-left: 8px; font-size: 12px; color: #909399">上传文件后自动识别，可点右上角「识别类型」重新识别</span>
            </el-form-item>
            <el-form-item label="年份">
              <el-input v-model="form.year" />
            </el-form-item>
            <el-form-item label="经度">
              <el-input v-model="form.longitude" />
            </el-form-item>
            <el-form-item label="纬度">
              <el-input v-model="form.latitude" />
            </el-form-item>
            <el-form-item label="概况">
              <el-input v-model="form.overview" type="textarea" :rows="3" />
            </el-form-item>
            <el-form-item label="备注">
              <el-input v-model="form.remark" type="textarea" :rows="2" />
            </el-form-item>
            <el-button type="primary" plain @click="onSaveMeta">保存基本信息</el-button>
          </el-form>

          <h3 class="sec" style="margin-top: 20px">
            附件
            <span v-if="extractSummary" class="extract-summary">{{ extractSummary }}</span>
          </h3>
          <el-empty v-if="!project?.files?.length" description="尚未上传" :image-size="60" />
          <ul class="file-list" v-else>
            <li v-for="f in project.files" :key="f.id">
              <span class="fname" :title="f.original_name">{{ f.original_name }}</span>
              <el-tag size="small" :type="f.has_text ? 'success' : 'info'">{{ f.file_ext }}</el-tag>
              <el-tooltip :content="extTooltip(f)" placement="top">
                <el-tag size="small" :type="extStatusType(f)" effect="plain">{{ extStatusLabel(f) }}</el-tag>
              </el-tooltip>
              <el-button link type="primary" size="small" @click="previewFile(f)">原文</el-button>
            </li>
          </ul>

          <h3 class="sec" style="margin-top: 20px">导出历史</h3>
          <el-empty v-if="!project?.exports?.length" description="无" :image-size="48" />
          <ul class="file-list" v-else>
            <li v-for="e in project.exports" :key="e.id">
              <span class="fname">{{ e.file_name }}</span>
              <el-button link type="primary" size="small" @click="downloadExport(e.id, e.file_name)">下载</el-button>
            </li>
          </ul>
        </div>
      </el-col>

      <el-col :span="16">
        <div class="card">
          <div class="table-toolbar">
            <h3 class="sec" style="margin: 0">监测条目（校对）</h3>
            <div>
              <el-button size="small" @click="addRow">新增行</el-button>
              <el-button size="small" type="danger" plain :disabled="!selected.length" @click="removeSelected">
                删除选中
              </el-button>
            </div>
          </div>
          <el-table
            :data="items"
            border
            size="small"
            height="620"
            @selection-change="(v) => (selected = v)"
          >
            <el-table-column type="selection" width="42" />
            <el-table-column label="类别" min-width="110">
              <template #default="{ row }">
                <el-input v-model="row.category" size="small" />
              </template>
            </el-table-column>
            <el-table-column label="编号" width="100">
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
            <el-table-column label="年次数" width="90">
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
      </el-col>
    </el-row>

    <el-drawer v-model="textVisible" title="抽取原文" size="45%">
      <pre class="raw-text">{{ previewText }}</pre>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  detectType,
  downloadExport,
  exportProject,
  getFileText,
  getProject,
  parseProject,
  saveItems,
  updateProject,
  uploadFiles,
} from '../api'

const props = defineProps({ id: { type: [String, Number], required: true } })

const loading = ref(false)
const uploading = ref(false)
const parsing = ref(false)
const detecting = ref(false)
const saving = ref(false)
const exporting = ref(false)
const project = ref(null)
const form = ref(null)
const items = ref([])
const selected = ref([])
const textVisible = ref(false)
const previewText = ref('')

function statusLabel(s) {
  return (
    {
      draft: '草稿',
      reviewing: '校对中',
      confirmed: '已确认',
      exported: '已导出',
      parse_failed: '解析失败',
    }[s] || s
  )
}
function statusType(s) {
  return (
    {
      draft: 'info',
      reviewing: 'warning',
      confirmed: 'success',
      exported: 'success',
      parse_failed: 'danger',
    }[s] || ''
  )
}

const extractSummary = computed(() => {
  const files = project.value?.files || []
  if (!files.length) return ''
  const ok = files.filter((f) => f.extract_status === 'success').length
  return `${ok}/${files.length} 个文件已提取`
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
    category: '',
    outlet_code: '',
    outlet_name: '',
    point_location: '',
    factors: '',
    sample_freq: '',
    period_freq: '',
    monitor_days: '',
    samples_per_day: '',
    annual_times: '',
    months_plan: '',
    standard_text: '',
    remark: '',
    sort_order: items.value.length,
  }
}

async function load() {
  loading.value = true
  try {
    const { data } = await getProject(props.id)
    project.value = data
    form.value = {
      name: data.name,
      client_name: data.client_name,
      address: data.address,
      contact: data.contact,
      phone: data.phone,
      project_type: data.project_type,
      year: data.year || '',
      longitude: data.longitude,
      latitude: data.latitude,
      overview: data.overview,
      remark: data.remark,
    }
    items.value = (data.items || []).map((i) => ({ ...i }))
  } finally {
    loading.value = false
  }
}

async function onUpload({ file }) {
  uploading.value = true
  try {
    const { data } = await uploadFiles(props.id, [file])
    project.value = data
    form.value.project_type = data.project_type
    const label = data.project_type === 'basic' ? '基础/单次' : '年度'
    const f = (data.files || []).find((x) => x.original_name === file.name)
    let msg = `已上传 ${file.name}，自动识别类型：${label}`
    if (f && f.extract_status === 'success') {
      msg += '，文本提取完成'
      ElMessage.success(msg)
    } else if (f && f.extract_status === 'failed') {
      ElMessage.warning(`已上传 ${file.name}，但文本提取失败：${f.extract_error}`)
    } else if (f) {
      ElMessage.warning(`已上传 ${file.name}，但未提取到文本，无法进行 AI 解析`)
    } else {
      ElMessage.success(msg)
    }
  } finally {
    uploading.value = false
  }
}

async function onParse() {
  parsing.value = true
  try {
    const { data } = await parseProject(props.id)
    ElMessage.success(data.message || `解析完成，共 ${data.item_count} 条`)
    await load()
  } finally {
    parsing.value = false
  }
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

watch(
  () => props.id,
  () => load(),
  { immediate: false }
)
onMounted(load)
</script>

<style scoped>
.actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}
.sec {
  font-size: 14px;
  margin: 0 0 12px;
  color: #303133;
}
.extract-summary {
  margin-left: 8px;
  font-size: 12px;
  font-weight: normal;
  color: #909399;
}
.file-list {
  list-style: none;
  padding: 0;
  margin: 0;
}
.file-list li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px solid #f0f0f0;
  font-size: 13px;
}
.fname {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.table-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.raw-text {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  line-height: 1.5;
  margin: 0;
}
</style>
