<template>
  <div class="boundary-block">
    <div class="boundary-header">
      <el-icon class="boundary-icon"><Lock /></el-icon>
      <span class="boundary-title">系统已关机 · 关系边界</span>
    </div>

    <div class="boundary-message">{{ report.shutdown_message }}</div>

    <div class="boundary-meta">
      <div class="meta-row">
        <span class="meta-label">触发原因</span>
        <span class="meta-value">{{ report.reason }}</span>
      </div>
      <div class="meta-row">
        <span class="meta-label">判定来源</span>
        <span class="meta-value">
          <el-tag size="small" effect="plain" :type="categoryTagType">{{ categoryLabel }}</el-tag>
          <span v-if="report.matched_rule" class="matched">命中规则：{{ report.matched_rule }}</span>
        </span>
      </div>
    </div>

    <el-alert
      :type="report.persisted ? 'warning' : 'success'"
      :closable="false"
      class="boundary-note"
      :title="report.note"
    />

    <div class="boundary-explain">
      这不是分析失败，而是系统按架构 5.3.4 主动关机：当决策对象是一个具体的、平等的他人时，
      任何量化都是物化。请用你的直觉和真诚去应对，而不是用公式去计算。
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { BoundaryReport } from '../../types'

const props = defineProps<{ report: BoundaryReport }>()

const CATEGORY_LABELS: Record<string, string> = {
  hard_rule: '硬规则匹配',
  semantic: '语义判定',
  none: '未触发',
}

const categoryLabel = computed(() => CATEGORY_LABELS[props.report.category] ?? props.report.category)

const categoryTagType = computed<'warning' | 'info'>(() =>
  props.report.category === 'hard_rule' ? 'warning' : 'info',
)
</script>

<style scoped>
.boundary-block {
  border: 1px solid #e4e7ed;
  border-left: 4px solid #909399;
  border-radius: 8px;
  padding: 16px 18px;
  background: #fafafa;
}
.boundary-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 12px;
}
.boundary-icon {
  color: #909399;
}
.boundary-title {
  font-size: 14px;
  font-weight: 600;
  color: #4e5969;
}
.boundary-message {
  font-size: 15px;
  line-height: 1.9;
  color: #1f2329;
  margin-bottom: 14px;
}
.boundary-meta {
  font-size: 13px;
  margin-bottom: 12px;
}
.meta-row {
  display: flex;
  gap: 10px;
  margin-bottom: 6px;
  line-height: 1.7;
}
.meta-label {
  flex: none;
  width: 64px;
  color: #8f959e;
}
.meta-value {
  color: #4e5969;
}
.matched {
  margin-left: 8px;
  color: #8f959e;
}
.boundary-note {
  margin-bottom: 12px;
}
.boundary-explain {
  font-size: 12px;
  line-height: 1.8;
  color: #a0a4ab;
}
</style>
