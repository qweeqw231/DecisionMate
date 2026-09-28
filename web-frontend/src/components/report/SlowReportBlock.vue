<template>
  <div class="slow-block">
    <!-- 综合建议 -->
    <div class="recommendation-wrap">
      <el-tag size="small" type="success" effect="plain" class="loop-tag">慢回路 · 多Agent会商</el-tag>
      <el-tag
        v-if="report.conflict_detected"
        size="small"
        type="danger"
        effect="light"
        class="conflict-tag"
      >
        分身意见存在分歧
      </el-tag>
      <div class="recommendation">{{ report.recommendation }}</div>
    </div>

    <!-- 关键指标 -->
    <div class="metrics">
      <div class="metric">
        <div class="metric-label">凯利值 f*</div>
        <div class="metric-value" :class="{ negative: report.f_star < 0 }">
          {{ report.f_star.toFixed(2) }}
        </div>
      </div>
      <div class="metric">
        <div class="metric-label">风险等级</div>
        <div class="metric-value">
          <el-tag size="small" :type="riskTagType(report.risk_level)">{{ report.risk_level }}</el-tag>
        </div>
      </div>
      <div class="metric">
        <div class="metric-label">场景类型</div>
        <div class="metric-value scene-type" :title="report.scenario_type">
          {{ report.scenario_type || '—' }}
        </div>
      </div>
    </div>

    <!-- 分身投票 -->
    <div v-if="report.persona_results?.length" class="section">
      <div class="section-title">分身会商</div>
      <PersonaVoteTable :votes="report.persona_results" />
    </div>

    <!-- 场景策略时间线 -->
    <div v-if="report.scene_result" class="section">
      <div class="section-title">场景策略</div>
      <ScenarioTimeline :scene="report.scene_result" />
    </div>

    <!-- 量化 / 风险意见 -->
    <el-collapse class="detail-collapse">
      <el-collapse-item title="量化分析意见" name="quant">
        <div class="detail-text">{{ report.quant_opinion }}</div>
      </el-collapse-item>
      <el-collapse-item title="风险评估意见" name="risk">
        <div class="detail-text">{{ report.risk_opinion }}</div>
      </el-collapse-item>
      <el-collapse-item title="计算过程" name="calc">
        <div class="detail-text calc">{{ report.calculation_detail }}</div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import type { DecisionReport } from '../../types'
import { riskTagType } from '../../utils/report'
import PersonaVoteTable from './PersonaVoteTable.vue'
import ScenarioTimeline from './ScenarioTimeline.vue'

defineProps<{ report: DecisionReport }>()
</script>

<style scoped>
.loop-tag,
.conflict-tag {
  margin-bottom: 8px;
}
.conflict-tag {
  margin-left: 6px;
}
.recommendation {
  font-size: 15px;
  line-height: 1.7;
  white-space: pre-wrap;
}
.metrics {
  display: flex;
  gap: 12px;
  margin: 14px 0;
}
.metric {
  flex: 1;
  background: #f7f8fa;
  border-radius: 8px;
  padding: 10px;
  text-align: center;
}
.metric-label {
  font-size: 12px;
  color: #8f959e;
}
.metric-value {
  margin-top: 4px;
  font-size: 18px;
  font-weight: 600;
}
.metric-value.negative {
  color: #f53f3f;
}
.scene-type {
  font-size: 13px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.section {
  margin-top: 14px;
}
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: #4e5969;
  margin-bottom: 8px;
}
.detail-text {
  font-size: 13px;
  line-height: 1.7;
  color: #4e5969;
  white-space: pre-wrap;
}
.detail-text.calc {
  font-family: Consolas, 'Courier New', monospace;
  font-size: 12px;
}
</style>
