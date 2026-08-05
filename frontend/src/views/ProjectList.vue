<template>
  <div class="page">
    <div class="page-header">
      <h1 class="page-title">项目列表</h1>
      <el-button type="primary" @click="showCreate = true">新建项目</el-button>
    </div>

    <div class="card filters">
      <el-input
        v-model="query.q"
        placeholder="搜索项目/客户"
        clearable
        style="width: 220px"
        @clear="load"
        @keyup.enter="load"
      />
      <el-select v-model="query.project_type" clearable placeholder="类型" style="width: 140px" @change="load">
        <el-option label="年度" value="annual" />
        <el-option label="基础/单次" value="basic" />
      </el-select>
      <el-select v-model="query.status" clearable placeholder="状态" style="width: 140px" @change="load">
        <el-option label="草稿" value="draft" />
        <el-option label="校对中" value="reviewing" />
        <el-option label="已确认" value="confirmed" />
        <el-option label="已导出" value="exported" />
        <el-option label="解析失败" value="parse_failed" />
      </el-select>
      <el-button @click="load">查询</el-button>
    </div>

    <div class="card" style="margin-top: 12px; padding: 0">
      <el-table :data="rows" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="项目名称" min-width="200" show-overflow-tooltip />
        <el-table-column prop="client_name" label="客户" min-width="140" show-overflow-tooltip />
        <el-table-column label="类型" width="100">
          <template #default="{ row }">
            {{ row.project_type === 'basic' ? '基础/单次' : '年度' }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="item_count" label="条目" width="70" />
        <el-table-column prop="file_count" label="附件" width="70" />
        <el-table-column prop="year" label="年份" width="90" />
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="$router.push(`/projects/${row.id}`)">打开</el-button>
            <el-button link type="danger" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="showCreate" title="新建项目" width="520px" destroy-on-close>
      <el-form label-width="90px">
        <el-form-item label="项目名称">
          <el-input v-model="form.name" placeholder="可上传后由解析填充" />
        </el-form-item>
        <el-form-item label="客户名称">
          <el-input v-model="form.client_name" />
        </el-form-item>
        <el-form-item label="年份">
          <el-input v-model="form.year" placeholder="如 2026" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="onCreate">创建并打开</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createProject, deleteProject, listProjects } from '../api'

const router = useRouter()
const loading = ref(false)
const rows = ref([])
const showCreate = ref(false)
const creating = ref(false)
const query = reactive({ q: '', project_type: '', status: '' })
const form = reactive({ name: '', client_name: '', year: '' })

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

async function load() {
  loading.value = true
  try {
    const params = {}
    if (query.q) params.q = query.q
    if (query.project_type) params.project_type = query.project_type
    if (query.status) params.status = query.status
    const { data } = await listProjects(params)
    rows.value = data
  } finally {
    loading.value = false
  }
}

async function onCreate() {
  creating.value = true
  try {
    const { data } = await createProject({ ...form })
    showCreate.value = false
    ElMessage.success('已创建')
    router.push(`/projects/${data.id}`)
  } finally {
    creating.value = false
  }
}

async function onDelete(row) {
  await ElMessageBox.confirm(`确认删除「${row.name || row.id}」？`, '删除', { type: 'warning' })
  await deleteProject(row.id)
  ElMessage.success('已删除')
  load()
}

onMounted(load)
</script>

<style scoped>
.filters {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
}
</style>
