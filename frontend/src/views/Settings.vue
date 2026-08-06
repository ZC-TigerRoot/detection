<template>
  <div class="settings-container">
    <el-card class="settings-card">
      <template #header>
        <div class="card-header">
          <span class="title">LLM 设置</span>
          <el-button type="primary" @click="handleSave" :loading="saving">保存配置</el-button>
        </div>
      </template>

      <el-form :model="form" label-width="140px" :rules="rules" ref="formRef">
        <el-form-item label="Base URL" prop="llm_base_url">
          <el-input
            v-model="form.llm_base_url"
            placeholder="https://api.deepseek.com/v1"
            clearable
          />
          <div class="form-hint">LLM API 的基础 URL（OpenAI 兼容格式）</div>
        </el-form-item>

        <el-form-item label="API Key" prop="llm_api_key">
          <el-input
            v-model="form.llm_api_key"
            type="password"
            placeholder="填写后自动掩码保存"
            show-password
            clearable
          />
          <div class="form-hint">
            <span v-if="form.api_key_set" style="color: #67c23a">✓ 已设置</span>
            <span v-else style="color: #909399">未配置将使用本地启发式解析</span>
          </div>
        </el-form-item>

        <el-form-item label="模型名称" prop="llm_model">
          <el-input v-model="form.llm_model" placeholder="deepseek-chat" clearable />
          <div class="form-hint">如 deepseek-chat、gpt-4o、gpt-3.5-turbo 等</div>
        </el-form-item>

        <el-form-item label="超时时间（秒）" prop="llm_timeout">
          <el-input-number
            v-model="form.llm_timeout"
            :min="10"
            :max="600"
            :step="10"
            controls-position="right"
          />
          <div class="form-hint">单次请求的最大等待时间</div>
        </el-form-item>

        <el-form-item label="最大输入字符数" prop="llm_max_input_chars">
          <el-input-number
            v-model="form.llm_max_input_chars"
            :min="10000"
            :max="500000"
            :step="10000"
            controls-position="right"
          />
          <div class="form-hint">文件提取文本超过此长度时自动截断</div>
        </el-form-item>

        <el-form-item>
          <el-space>
            <el-button type="primary" @click="handleSave" :loading="saving">
              保存配置
            </el-button>
            <el-button @click="handleTest" :loading="testing" :disabled="!form.api_key_set">
              测试连接
            </el-button>
            <el-button @click="handleReset" :disabled="saving">重置</el-button>
          </el-space>
        </el-form-item>
      </el-form>

      <el-alert
        v-if="testResult"
        :type="testResult.ok ? 'success' : 'error'"
        :title="testResult.message"
        :closable="true"
        @close="testResult = null"
        show-icon
        style="margin-top: 20px"
      >
        <template v-if="testResult.ok">
          <div>模型：{{ testResult.model }}</div>
          <div>延迟：{{ testResult.latency_ms }} ms</div>
        </template>
      </el-alert>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getLLMSettings, updateLLMSettings, testLLMConnection } from '../api'

const formRef = ref(null)
const form = ref({
  llm_base_url: '',
  llm_model: '',
  llm_timeout: 120,
  llm_max_input_chars: 60000,
  llm_api_key: '',
  api_key_set: false,
})

const originalForm = ref({})
const saving = ref(false)
const testing = ref(false)
const testResult = ref(null)

const rules = {
  llm_base_url: [
    { required: true, message: '请输入 Base URL', trigger: 'blur' },
    {
      pattern: /^https?:\/\/.+/,
      message: 'Base URL 必须以 http:// 或 https:// 开头',
      trigger: 'blur',
    },
  ],
  llm_model: [{ required: true, message: '请输入模型名称', trigger: 'blur' }],
  llm_timeout: [{ required: true, message: '请输入超时时间', trigger: 'blur' }],
  llm_max_input_chars: [
    { required: true, message: '请输入最大输入字符数', trigger: 'blur' },
  ],
}

async function loadSettings() {
  try {
    const res = await getLLMSettings()
    form.value = {
      llm_base_url: res.data.llm_base_url,
      llm_model: res.data.llm_model,
      llm_timeout: res.data.llm_timeout,
      llm_max_input_chars: res.data.llm_max_input_chars,
      llm_api_key: res.data.api_key_masked,
      api_key_set: res.data.api_key_set,
    }
    originalForm.value = { ...form.value }
  } catch (err) {
    ElMessage.error('加载设置失败')
  }
}

async function handleSave() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }

  saving.value = true
  testResult.value = null
  try {
    const payload = {
      llm_base_url: form.value.llm_base_url,
      llm_model: form.value.llm_model,
      llm_timeout: form.value.llm_timeout,
      llm_max_input_chars: form.value.llm_max_input_chars,
    }
    // 如果 API Key 字段包含掩码（***），说明用户没改，不传
    if (form.value.llm_api_key && !form.value.llm_api_key.includes('***')) {
      payload.llm_api_key = form.value.llm_api_key
    }
    const res = await updateLLMSettings(payload)
    form.value.llm_api_key = res.data.api_key_masked
    form.value.api_key_set = res.data.api_key_set
    originalForm.value = { ...form.value }
    ElMessage.success('保存成功')
  } catch (err) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

async function handleTest() {
  testing.value = true
  testResult.value = null
  try {
    const res = await testLLMConnection()
    testResult.value = res.data
    if (res.data.ok) {
      ElMessage.success('连接测试成功')
    } else {
      ElMessage.warning('连接测试失败')
    }
  } catch (err) {
    ElMessage.error('测试请求失败')
  } finally {
    testing.value = false
  }
}

function handleReset() {
  form.value = { ...originalForm.value }
  testResult.value = null
  formRef.value?.clearValidate()
}

onMounted(() => {
  loadSettings()
})
</script>

<style scoped>
.settings-container {
  padding: 24px;
  max-width: 900px;
  margin: 0 auto;
}

.settings-card {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.title {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}

.form-hint {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
  line-height: 1.4;
}

:deep(.el-form-item__label) {
  font-weight: 500;
}

:deep(.el-input-number) {
  width: 200px;
}
</style>
