<template>
  <div class="composer">
    <PersonaSelector :disabled="loading" />
    <el-input
      v-model="text"
      type="textarea"
      :rows="1"
      :autosize="{ minRows: 1, maxRows: 6 }"
      resize="none"
      placeholder="描述你面临的决策场景，Enter 发送 / Shift+Enter 换行"
      :disabled="loading"
      class="composer-input"
      @keydown="onKeydown"
    />
    <el-button
      v-if="!loading"
      type="primary"
      circle
      class="send-btn"
      :disabled="!text.trim()"
      @click="submit"
    >
      <el-icon><Promotion /></el-icon>
    </el-button>
    <el-button v-else type="danger" circle class="send-btn" @click="emit('abort')">
      <el-icon><VideoPause /></el-icon>
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import PersonaSelector from './PersonaSelector.vue'

withDefaults(defineProps<{ loading?: boolean }>(), { loading: false })
const emit = defineEmits<{
  (e: 'send', text: string): void
  (e: 'abort'): void
}>()

const text = ref('')

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    submit()
  }
}

function submit() {
  const value = text.value.trim()
  if (!value) return
  emit('send', value)
  text.value = ''
}
</script>

<style scoped>
.composer {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  background: #fff;
  border: 1px solid #e5e6eb;
  border-radius: 12px;
  padding: 6px 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.05);
}
.composer-input {
  flex: 1;
}
.composer-input :deep(.el-textarea__inner) {
  border: none;
  box-shadow: none !important;
  padding: 8px 4px;
  font-size: 14px;
}
.send-btn {
  flex-shrink: 0;
  margin-bottom: 2px;
}
</style>
