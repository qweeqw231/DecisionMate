<template>
  <div class="archive-panel">
    <el-divider content-position="left">
      <span class="archive-title">
        <el-icon><Files /></el-icon>
        复盘归档报告
      </span>
    </el-divider>

    <div class="archive-section">
      <span class="label">初始 f*：</span>{{ report.initial_f_star.toFixed(2) }}
      <span class="label" style="margin-left: 16px">反馈类型：</span>
      <el-tag size="small" :type="feedbackTagType" effect="plain">{{ feedbackLabel }}</el-tag>
    </div>

    <div class="archive-section">
      <div class="sub-title">偏差分析</div>
      <div class="text">{{ report.deviation_analysis }}</div>
    </div>

    <div v-if="factorEntries.length" class="archive-section">
      <div class="sub-title">能力因子更新</div>
      <div v-for="([name, change]) in factorEntries" :key="name" class="factor-row">
        <span class="factor-name">{{ name }}</span>
        <span class="factor-old">{{ Number(change.old).toFixed(2) }}</span>
        <el-icon class="arrow"><Right /></el-icon>
        <span class="factor-new">{{ Number(change.new).toFixed(2) }}</span>
      </div>
    </div>

    <div v-if="report.new_factor_proposal" class="archive-section">
      <div class="sub-title">新因子提议</div>
      <div class="text">
        {{ report.new_factor_proposal.factor_name }}（建议值
        {{ report.new_factor_proposal.suggested_value }}）：{{ report.new_factor_proposal.basis }}
        <el-tag
          v-if="report.new_factor_proposal.data_insufficient"
          size="small"
          type="warning"
          effect="plain"
          style="margin-left: 6px"
        >
          支撑数据不足（&lt;3 条）
        </el-tag>
      </div>
    </div>

    <div v-if="report.reusable_pattern" class="archive-section">
      <div class="sub-title">可复用模式</div>
      <div class="text">{{ report.reusable_pattern }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ArchiveReport } from '../../types'

const props = defineProps<{ report: ArchiveReport }>()

const factorEntries = computed(() => Object.entries(props.report.factor_updates || {}))
const feedbackLabel = computed(() =>
  ({ useful: '决策有效', inaccurate: '决策不准确', custom: '自定义反馈' }[props.report.feedback_type]
    || props.report.feedback_type),
)
const feedbackTagType = computed<'success' | 'danger' | 'info'>(() =>
  ({ useful: 'success', inaccurate: 'danger', custom: 'info' } as const)[
    props.report.feedback_type as 'useful' | 'inaccurate' | 'custom'
  ] || 'info',
)
</script>

<style scoped>
.archive-title {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: #4e5969;
}
.archive-section {
  margin-bottom: 10px;
  font-size: 13px;
}
.label {
  color: #8f959e;
}
.sub-title {
  font-weight: 600;
  color: #4e5969;
  margin-bottom: 4px;
}
.text {
  line-height: 1.7;
  color: #1f2329;
  white-space: pre-wrap;
}
.factor-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}
.factor-name {
  min-width: 110px;
  color: #4e5969;
}
.factor-old {
  color: #8f959e;
}
.arrow {
  color: #4080ff;
}
.factor-new {
  font-weight: 600;
  color: #1f2329;
}
</style>
