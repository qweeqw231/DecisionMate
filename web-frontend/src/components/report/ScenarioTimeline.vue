<template>
  <div class="scene">
    <div class="scene-head">
      <el-icon class="head-icon"><Timer /></el-icon>
      <span class="scene-type">{{ scene.scene_type || '场景策略' }}</span>
      <el-tag v-if="scene.complex_type" size="small" effect="plain" type="warning" class="complex-tag">
        {{ scene.complex_type }}
      </el-tag>
    </div>
    <div v-if="scene.timeline_summary" class="timeline-summary">{{ scene.timeline_summary }}</div>

    <el-timeline v-if="scene.strategies?.length" class="strategies">
      <el-timeline-item
        v-for="(s, i) in scene.strategies"
        :key="i"
        :timestamp="s.date_range"
        placement="top"
        type="primary"
      >
        <div class="strategy-name">{{ s.strategy_name }}<span class="phase"> · {{ s.phase }}</span></div>
        <div class="strategy-suggestion">{{ s.suggestion }}</div>
        <div v-if="s.reference" class="strategy-ref">参考：{{ s.reference }}</div>
      </el-timeline-item>
    </el-timeline>

    <el-collapse v-if="scene.reasoning" class="reasoning-collapse">
      <el-collapse-item title="场景识别推理过程" name="r">
        <div class="reasoning-text">{{ scene.reasoning }}</div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import type { SceneResult } from '../../types'

defineProps<{ scene: SceneResult }>()
</script>

<style scoped>
.scene-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 14px;
}
.head-icon {
  color: #4080ff;
}
.complex-tag {
  margin-left: 4px;
}
.timeline-summary {
  margin: 8px 0 4px;
  font-size: 13px;
  color: #4e5969;
  line-height: 1.6;
}
.strategies {
  margin-top: 12px;
  padding-left: 4px;
}
.strategy-name {
  font-weight: 600;
  font-size: 13px;
}
.phase {
  font-weight: 400;
  color: #8f959e;
}
.strategy-suggestion {
  margin-top: 4px;
  font-size: 13px;
  line-height: 1.7;
  color: #1f2329;
}
.strategy-ref {
  margin-top: 4px;
  font-size: 12px;
  color: #8f959e;
}
.reasoning-text {
  font-size: 12px;
  color: #646a73;
  line-height: 1.7;
  white-space: pre-wrap;
}
</style>
