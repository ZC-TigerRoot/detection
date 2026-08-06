<template>
  <el-dialog
    v-model="visible"
    width="720px"
    top="8vh"
    align-center
    :close-on-click-modal="false"
    :close-on-press-escape="canClose"
    :show-close="canClose"
    :destroy-on-close="false"
    class="parse-dialog"
    @closed="onClosed"
  >
    <template #header>
      <div class="pd-header">
        <div class="pd-orb" :class="orbClass">
          <el-icon v-if="phase === 'error'"><CircleCloseFilled /></el-icon>
          <el-icon v-else-if="phase === 'done'"><SuccessFilled /></el-icon>
          <el-icon v-else><MagicStick /></el-icon>
        </div>
        <div class="pd-head-text">
          <div class="pd-title">{{ headTitle }}</div>
          <div class="pd-sub">
            {{ stageMessage }}
            <span class="pd-timer">{{ elapsedText }}</span>
          </div>
        </div>
      </div>
    </template>

    <div class="pd-body">
      <el-steps :active="activeStep" align-center finish-status="success" :process-status="stepStatus">
        <el-step v-for="s in STEPS" :key="s.key" :title="s.title" />
      </el-steps>

      <el-progress
        :percentage="percent"
        :status="phase === 'error' ? 'exception' : phase === 'done' ? 'success' : ''"
        :stroke-width="6"
        :indeterminate="phase === 'running' && percent < 100"
        :duration="2"
        class="pd-progress"
      />

      <div v-if="phase === 'running' && !streamText" class="pd-waiting">
        <span class="pd-dot" /><span class="pd-dot" /><span class="pd-dot" />
        <span class="pd-waiting-text">模型正在阅读方案原文，首个字通常需要 5～20 秒，请勿关闭页面</span>
      </div>

      <div v-if="hasStream" class="pd-stream">
        <div class="pd-stream-bar">
          <el-radio-group v-model="tab" size="small">
            <el-radio-button v-if="thought" value="thought">推理过程</el-radio-button>
            <el-radio-button value="output">解析输出</el-radio-button>
          </el-radio-group>
          <div class="pd-stream-meta">
            <el-icon class="pd-live" v-if="phase === 'running'"><Loading /></el-icon>
            {{ streamText.length }} 字
          </div>
        </div>
        <pre ref="streamEl" class="pd-stream-text" :class="{ 'is-output': tab === 'output' }">{{ streamText }}<span
            v-if="phase === 'running'"
            class="pd-caret"
          /></pre>
      </div>

      <el-alert
        v-if="phase === 'error'"
        type="error"
        :title="errorMessage"
        :closable="false"
        show-icon
      />
      <el-alert
        v-else-if="phase === 'done'"
        type="success"
        :title="`解析完成，共提取 ${itemCount} 条监测条目，请在右侧表格中核对`"
        :closable="false"
        show-icon
      />
    </div>

    <template #footer>
      <div class="pd-footer-content">
        <div class="pd-token-info" v-if="tokenText">{{ tokenText }}</div>
        <div class="pd-footer-actions">
          <el-button v-if="phase === 'running'" @click="cancel">中止解析</el-button>
          <el-button v-if="phase === 'error'" type="primary" @click="start">重试</el-button>
          <el-button v-if="canClose" :type="phase === 'done' ? 'primary' : 'default'" @click="visible = false">
            {{ phase === 'done' ? '开始校对' : '关闭' }}
          </el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import {
  CircleCloseFilled,
  Loading,
  MagicStick,
  SuccessFilled,
} from '@element-plus/icons-vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  projectId: { type: [Number, String], required: true },
})
const emit = defineEmits(['update:modelValue', 'done', 'failed'])

const STEPS = [
  { key: 'prepare', title: '读取原文' },
  { key: 'llm_call', title: 'AI 解析' },
  { key: 'parse_json', title: '结构化' },
  { key: 'save', title: '写入' },
]

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const phase = ref('idle') // idle | running | done | error
const stage = ref('prepare')
const stageMessage = ref('')
const thought = ref('')
const output = ref('')
const tab = ref('output')
const errorMessage = ref('')
const itemCount = ref(0)
const tokenUsage = ref(null)
const elapsed = ref(0)
const streamEl = ref(null)

let controller = null
let timer = null

const canClose = computed(() => phase.value === 'done' || phase.value === 'error')
const hasStream = computed(() => Boolean(thought.value || output.value))
const streamText = computed(() => (tab.value === 'thought' ? thought.value : output.value))

const activeStep = computed(() => {
  if (phase.value === 'done') return STEPS.length
  const i = STEPS.findIndex((s) => s.key === stage.value)
  return i < 0 ? 0 : i
})

const stepStatus = computed(() => (phase.value === 'error' ? 'error' : 'process'))

const percent = computed(() => {
  if (phase.value === 'done') return 100
  if (phase.value === 'error') return 100
  const base = (activeStep.value / STEPS.length) * 100
  // AI 解析阶段按已输出字数做一个平滑的视觉推进，上限不越过本阶段
  if (stage.value === 'llm_call') {
    const chars = output.value.length + thought.value.length
    const grow = Math.min(20, (chars / 1600) * 20)
    return Math.round(base + grow)
  }
  return Math.round(base)
})

const orbClass = computed(() => ({
  'is-running': phase.value === 'running',
  'is-done': phase.value === 'done',
  'is-error': phase.value === 'error',
}))

const headTitle = computed(() => {
  if (phase.value === 'error') return 'AI 解析失败'
  if (phase.value === 'done') return 'AI 解析完成'
  return 'AI 正在解析方案'
})

const elapsedText = computed(() => {
  const s = elapsed.value
  if (!s) return ''
  const m = Math.floor(s / 60)
  const r = s % 60
  return m ? `· 已用 ${m}分${r}秒` : `· 已用 ${r}秒`
})

const tokenText = computed(() => {
  const u = tokenUsage.value
  if (!u) return ''
  const input = u.prompt_tokens || 0
  const outputTokens = u.completion_tokens || 0
  const total = u.total_tokens || input + outputTokens
  if (!total) return ''
  const n = (v) => v.toLocaleString('en-US')
  if (input || outputTokens) {
    return `本次花费 Token：输入 ${n(input)} · 输出 ${n(outputTokens)} · 共 ${n(total)}`
  }
  return `本次花费 Token：${n(total)}`
})

function reset() {
  phase.value = 'running'
  stage.value = 'prepare'
  stageMessage.value = '正在合并附件文本…'
  thought.value = ''
  output.value = ''
  tab.value = 'output'
  errorMessage.value = ''
  itemCount.value = 0
  tokenUsage.value = null
  elapsed.value = 0
}

function startTimer() {
  stopTimer()
  timer = setInterval(() => {
    elapsed.value += 1
  }, 1000)
}
function stopTimer() {
  if (timer) clearInterval(timer)
  timer = null
}

function handleEvent(type, data) {
  if (type === 'stage') {
    stage.value = data.stage || stage.value
    stageMessage.value = data.message || ''
  } else if (type === 'thought') {
    thought.value += data.content || ''
    if (tab.value !== 'thought' && !output.value) tab.value = 'thought'
    scrollStream()
  } else if (type === 'delta') {
    output.value += data.content || ''
    if (tab.value === 'thought' && thought.value === '') tab.value = 'output'
    scrollStream()
  } else if (type === 'done') {
    itemCount.value = data.item_count || 0
    tokenUsage.value = data.usage || null
    stageMessage.value = `已写入 ${itemCount.value} 条监测条目`
    phase.value = 'done'
    stopTimer()
    emit('done', { itemCount: itemCount.value })
  } else if (type === 'error') {
    errorMessage.value = data.message || '未知错误'
    phase.value = 'error'
    stopTimer()
    emit('failed', errorMessage.value)
  }
}

function scrollStream() {
  nextTick(() => {
    const el = streamEl.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

async function start() {
  reset()
  startTimer()
  controller = new AbortController()

  try {
    const resp = await fetch(`/api/projects/${props.projectId}/parse-stream`, {
      method: 'POST',
      headers: { Accept: 'text/event-stream' },
      signal: controller.signal,
    })
    if (!resp.ok || !resp.body) {
      throw new Error(`服务返回 HTTP ${resp.status}`)
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''

    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // SSE 以空行分隔事件块
      const blocks = buffer.split('\n\n')
      buffer = blocks.pop() ?? ''
      for (const block of blocks) {
        let type = 'message'
        const dataLines = []
        for (const line of block.split('\n')) {
          if (line.startsWith('event:')) type = line.slice(6).trim()
          else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
        }
        if (!dataLines.length) continue
        try {
          handleEvent(type, JSON.parse(dataLines.join('\n')))
        } catch {
          /* 忽略单条无法解析的事件 */
        }
      }
    }

    if (phase.value === 'running') {
      errorMessage.value = '连接意外中断，解析可能未完成'
      phase.value = 'error'
      emit('failed', errorMessage.value)
    }
  } catch (err) {
    if (err?.name === 'AbortError') {
      errorMessage.value = '已中止解析'
      phase.value = 'error'
    } else {
      errorMessage.value = err?.message || '网络请求失败'
      phase.value = 'error'
      emit('failed', errorMessage.value)
    }
  } finally {
    stopTimer()
    controller = null
  }
}

function cancel() {
  controller?.abort()
}

function onClosed() {
  controller?.abort()
  stopTimer()
  phase.value = 'idle'
}

watch(
  () => props.modelValue,
  (v) => {
    if (v) start()
  }
)

onBeforeUnmount(() => {
  controller?.abort()
  stopTimer()
})
</script>

<style scoped>
.pd-header {
  display: flex;
  align-items: center;
  gap: 14px;
}
.pd-orb {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  color: #fff;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  flex: none;
}
.pd-orb.is-running {
  animation: pd-pulse 1.6s ease-in-out infinite;
}
.pd-orb.is-done {
  background: linear-gradient(135deg, #10b981, #34d399);
}
.pd-orb.is-error {
  background: linear-gradient(135deg, #ef4444, #f87171);
}
@keyframes pd-pulse {
  0%,
  100% {
    box-shadow: 0 0 0 0 rgba(99, 102, 241, 0.45);
  }
  50% {
    box-shadow: 0 0 0 10px rgba(99, 102, 241, 0);
  }
}
.pd-title {
  font-size: 16px;
  font-weight: 600;
  color: #111827;
  line-height: 1.3;
}
.pd-sub {
  font-size: 12px;
  color: #6b7280;
  margin-top: 3px;
}
.pd-timer {
  margin-left: 4px;
  color: #9ca3af;
}

.pd-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.pd-progress {
  margin-top: -4px;
}

.pd-waiting {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 14px 16px;
  border-radius: 8px;
  background: #f8fafc;
  border: 1px dashed #e2e8f0;
  font-size: 12px;
  color: #64748b;
}
.pd-waiting-text {
  margin-left: 6px;
}
.pd-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #818cf8;
  animation: pd-bounce 1.2s ease-in-out infinite;
}
.pd-dot:nth-child(2) {
  animation-delay: 0.15s;
}
.pd-dot:nth-child(3) {
  animation-delay: 0.3s;
}
@keyframes pd-bounce {
  0%,
  80%,
  100% {
    transform: translateY(0);
    opacity: 0.45;
  }
  40% {
    transform: translateY(-5px);
    opacity: 1;
  }
}

.pd-stream {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
}
.pd-stream-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  background: #f9fafb;
  border-bottom: 1px solid #e5e7eb;
}
.pd-stream-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #9ca3af;
}
.pd-live {
  animation: pd-spin 1s linear infinite;
}
@keyframes pd-spin {
  to {
    transform: rotate(360deg);
  }
}
.pd-stream-text {
  margin: 0;
  padding: 12px 14px;
  height: 200px;
  overflow: auto;
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  color: #374151;
  background: #fff;
}
.pd-stream-text.is-output {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  color: #1f2937;
  background: #fbfcfd;
}
.pd-caret {
  display: inline-block;
  width: 7px;
  height: 14px;
  margin-left: 2px;
  vertical-align: text-bottom;
  background: #6366f1;
  animation: pd-blink 1s step-end infinite;
}
@keyframes pd-blink {
  50% {
    opacity: 0;
  }
}

.pd-footer-content {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 14px;
  width: 100%;
}
.pd-footer-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.pd-token-info {
  font-size: 12px;
  color: #9ca3af;
  font-variant-numeric: tabular-nums;
}
</style>
