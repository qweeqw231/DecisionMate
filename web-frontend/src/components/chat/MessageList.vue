<template>
  <div ref="listEl" class="message-list">
    <div v-if="!store.messages.length && !store.isStreaming" class="welcome">
      <el-icon class="welcome-icon"><Compass /></el-icon>
      <div class="welcome-title">DecisionMate 个人决策支持系统</div>
      <div class="welcome-desc">
        描述你面临的决策场景，系统将调度量化、风险、场景策略多个 Agent 进行会商分析
      </div>
      <div class="welcome-examples">
        <div v-for="(ex, i) in examples" :key="i" class="example-item" @click="emit('example', ex)">
          {{ ex }}
        </div>
      </div>
    </div>

    <MessageBubble v-for="m in store.messages" :key="m.id" :message="m" />

    <!-- 流式分析进度 -->
    <div v-if="store.isStreaming" class="bubble-row assistant">
      <div class="avatar assistant">
        <el-icon><Cpu /></el-icon>
      </div>
      <div class="bubble assistant progress-bubble">
        <div class="progress-title">
          <el-icon class="is-loading"><Loading /></el-icon>
          {{ progressText }}
        </div>
        <el-steps :active="stepIndex" align-center :process-status="'process'" class="progress-steps">
          <el-step title="分身量化" v-if="hasPersonas" />
          <el-step title="风险评估" />
          <el-step title="场景策略" />
          <el-step title="融合结论" />
        </el-steps>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useConversationStore } from '../../stores/conversation'
import MessageBubble from './MessageBubble.vue'

const emit = defineEmits<{ (e: 'example', text: string): void }>()

const store = useConversationStore()
const listEl = ref<HTMLElement | null>(null)

const examples = [
  '有人插队我要不要当场制止',
  '我在想要不要花整个周末做深度复盘，下周还有飞控考试',
  '我5月23日软考，5月24日飞控，中间怎么安排？',
]

const stageLabels: Record<string, string> = {
  start: '正在接收请求…',
  fast: '直觉决策分析中…',
  quant: '量化分析中…',
  personas: '多个分身正在并行量化分析…',
  risk: '风险评估中…',
  scene: '场景策略分析中…',
  merge: '正在融合各分身结论…',
}

const hasPersonas = computed(
  () => store.streaming.stage !== 'fast' && store.streaming.stage !== 'quant',
)
const progressText = computed(() => {
  const base = stageLabels[store.streaming.stage] || '分析中…'
  if (store.streaming.stage === 'personas' && store.streaming.personaNames.length) {
    return `分身并行分析中：${store.streaming.personaNames.join('、')}`
  }
  return base
})
const stepIndex = computed(() => {
  const order = ['start', 'personas', 'quant', 'risk', 'scene', 'merge']
  const i = order.indexOf(store.streaming.stage)
  if (i < 0) return 0
  return hasPersonas.value ? Math.min(i, 3) : Math.max(0, i - 1)
})

watch(
  () => [store.messages.length, store.streaming.stage],
  async () => {
    await nextTick()
    const el = listEl.value
    if (el) el.scrollTop = el.scrollHeight
  },
)
</script>

<style scoped>
.message-list {
  height: 100%;
  overflow-y: auto;
  padding: 28px 24px 8px;
}
.welcome {
  text-align: center;
  padding: 90px 20px 40px;
}
.welcome-icon {
  font-size: 46px;
  color: #4080ff;
}
.welcome-title {
  margin-top: 14px;
  font-size: 22px;
  font-weight: 700;
}
.welcome-desc {
  margin-top: 10px;
  color: #8f959e;
  font-size: 14px;
}
.welcome-examples {
  margin-top: 28px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}
.example-item {
  width: min(480px, 90%);
  padding: 10px 16px;
  border: 1px solid #e5e6eb;
  border-radius: 10px;
  font-size: 13px;
  color: #4e5969;
  cursor: pointer;
  transition: all 0.15s;
}
.example-item:hover {
  border-color: #4080ff;
  color: #4080ff;
  background: #f5f9ff;
}
.progress-bubble {
  width: min(520px, 100%);
}
.progress-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #4e5969;
  margin-bottom: 14px;
}
.progress-steps {
  padding: 0 4px;
}
.bubble-row {
  display: flex;
  gap: 10px;
  margin-bottom: 22px;
}
.avatar {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.avatar.assistant {
  background: #e8f1ff;
  color: #4080ff;
}
.bubble {
  border-radius: 12px;
  padding: 12px 14px;
}
.bubble.assistant {
  background: #fff;
  border: 1px solid #eef0f2;
}
</style>
