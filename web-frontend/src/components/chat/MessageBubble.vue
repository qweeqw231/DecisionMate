<template>
  <div class="bubble-row" :class="message.role">
    <div class="avatar" :class="message.role">
      <el-icon v-if="message.role === 'user'"><User /></el-icon>
      <el-icon v-else><Cpu /></el-icon>
    </div>
    <div class="bubble-body">
      <div class="bubble" :class="message.role">
        <template v-if="message.role === 'user'">
          <div class="user-text">{{ message.content }}</div>
        </template>
        <template v-else>
          <ReportCard
            v-if="report"
            :report="report"
            :conv-id="message.conversation_id"
            :msg-id="message.id"
            :show-feedback="message.id > 0"
          />
          <div v-else class="raw-text">{{ message.content }}</div>
        </template>
      </div>
      <div v-if="message.role === 'assistant' && message.id > 0" class="bubble-actions">
        <CopyButton :text="message.content" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Message } from '../../types'
import { parseReport } from '../../utils/report'
import ReportCard from '../report/ReportCard.vue'
import CopyButton from '../common/CopyButton.vue'

const props = defineProps<{ message: Message }>()
const report = computed(() =>
  props.message.role === 'assistant' ? parseReport(props.message.content) : null,
)
</script>

<style scoped>
.bubble-row {
  display: flex;
  gap: 10px;
  margin-bottom: 22px;
}
.bubble-row.user {
  flex-direction: row-reverse;
}
.avatar {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  flex-shrink: 0;
}
.avatar.user {
  background: #4080ff;
  color: #fff;
}
.avatar.assistant {
  background: #e8f1ff;
  color: #4080ff;
}
.bubble-body {
  max-width: min(720px, 78%);
}
.bubble-row.user .bubble-body {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}
.bubble {
  border-radius: 12px;
  padding: 12px 14px;
}
.bubble.user {
  background: #4080ff;
}
.user-text {
  color: #fff;
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
}
.bubble.assistant {
  background: #fff;
  border: 1px solid #eef0f2;
}
.raw-text {
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
}
.bubble-actions {
  margin-top: 2px;
  opacity: 0;
  transition: opacity 0.15s;
}
.bubble-row:hover .bubble-actions {
  opacity: 1;
}
</style>
