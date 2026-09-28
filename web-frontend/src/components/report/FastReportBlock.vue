<template>
  <div class="fast-block">
    <el-tag size="small" type="info" effect="plain" class="loop-tag">快回路 · 直觉建议</el-tag>
    <div class="recommendation">{{ report.recommendation }}</div>
    <div v-if="report.note" class="note">{{ report.note }}</div>
  </div>
</template>

<script setup lang="ts">
import type { FastDecisionReport } from '../../types'

defineProps<{ report: FastDecisionReport }>()
</script>

<style scoped>
.loop-tag {
  margin-bottom: 8px;
}
.recommendation {
  font-size: 15px;
  line-height: 1.7;
  color: #1f2329;
  white-space: pre-wrap;
}
.note {
  margin-top: 10px;
  font-size: 12px;
  color: #8f959e;
  line-height: 1.6;
}
</style>
