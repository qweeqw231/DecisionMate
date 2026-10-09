<template>
  <div class="report-card">
    <BoundaryBlock v-if="isBoundary" :report="report as BoundaryReport" />
    <FastReportBlock v-else-if="isFast" :report="report as FastDecisionReport" />
    <template v-else>
      <SlowReportBlock :report="report as DecisionReport" />
      <!-- L1 执行中校准：只有落库的慢回路决策才有对应的决策记录 -->
      <ExecutionTracker v-if="msgId > 0" :conv-id="convId" :msg-id="msgId" />
    </template>
    <div v-if="showFeedback && msgId > 0" class="feedback-wrap">
      <FeedbackBar :conv-id="convId" :msg-id="msgId" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AnyReport, BoundaryReport, DecisionReport, FastDecisionReport } from '../../types'
import { isBoundaryReport, isFastReport } from '../../utils/report'
import BoundaryBlock from './BoundaryBlock.vue'
import ExecutionTracker from './ExecutionTracker.vue'
import FastReportBlock from './FastReportBlock.vue'
import SlowReportBlock from './SlowReportBlock.vue'
import FeedbackBar from './FeedbackBar.vue'

const props = withDefaults(
  defineProps<{
    report: AnyReport
    convId: number
    msgId: number
    showFeedback?: boolean
  }>(),
  { showFeedback: true },
)

const isFast = computed(() => isFastReport(props.report))
const isBoundary = computed(() => isBoundaryReport(props.report))
// 快回路与边界关机都不支持反馈（后端只对慢回路的决策记录开放反馈）
const showFeedback = computed(() => props.showFeedback && !isFast.value && !isBoundary.value)
</script>

<style scoped>
.report-card {
  width: 100%;
}
.feedback-wrap {
  margin-top: 12px;
}
</style>
