<template>
  <div class="report-card">
    <FastReportBlock v-if="isFast" :report="report as FastDecisionReport" />
    <SlowReportBlock v-else :report="report as DecisionReport" />
    <div v-if="showFeedback && msgId > 0" class="feedback-wrap">
      <FeedbackBar :conv-id="convId" :msg-id="msgId" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AnyReport, DecisionReport, FastDecisionReport } from '../../types'
import { isFastReport } from '../../utils/report'
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
// 快回路不支持反馈（后端 feedback 端点会拒绝）
const showFeedback = computed(() => props.showFeedback && !isFast.value)
</script>

<style scoped>
.report-card {
  width: 100%;
}
.feedback-wrap {
  margin-top: 12px;
}
</style>
