<template>
  <el-table :data="votes" size="small" border class="vote-table" :row-key="rowKey">
    <el-table-column type="expand">
      <template #default="{ row }">
        <div class="persona-detail">
          <div class="detail-head">
            <span class="detail-name">{{ row.persona_name || row.name }}</span>
            <el-tag
              v-if="row.risk_preference"
              size="small"
              :type="prefType(row.risk_preference)"
              effect="plain"
            >
              {{ prefLabel(row.risk_preference) }}
            </el-tag>
            <span class="detail-weight">会商权重 {{ (row.weight * 100).toFixed(0) }}%</span>
          </div>
          <div class="detail-opinion-title">该分身的分析意见</div>
          <div class="detail-reasoning">{{ row.reasoning || row.summary || '（该分身未返回分析意见）' }}</div>
        </div>
      </template>
    </el-table-column>
    <el-table-column label="分身" min-width="120">
      <template #default="{ row }">
        <span class="expand-hint">
          <el-icon><ArrowRight /></el-icon>
        </span>
        <span>{{ row.persona_name || row.name }}</span>
        <el-tag
          v-if="row.risk_preference"
          size="small"
          :type="prefType(row.risk_preference)"
          effect="plain"
          class="pref-tag"
        >
          {{ prefLabel(row.risk_preference) }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column label="权重" width="72" align="center">
      <template #default="{ row }">{{ (row.weight * 100).toFixed(0) }}%</template>
    </el-table-column>
    <el-table-column label="p（胜率）" width="82" align="center">
      <template #default="{ row }">{{ fmt(row.p) }}</template>
    </el-table-column>
    <el-table-column label="b（赔率）" width="82" align="center">
      <template #default="{ row }">{{ fmt(row.b) }}</template>
    </el-table-column>
    <el-table-column label="f*（凯利值）" width="100" align="center">
      <template #default="{ row }">
        <span :class="{ negative: row.f_star < 0 }">{{ fmt(row.f_star) }}</span>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import type { PersonaVote } from '../../types'

defineProps<{ votes: PersonaVote[] }>()

// 必须返回稳定 key：原先带递增计数器的写法每次渲染都不同，
// 会导致 Element Plus 无法追踪行状态、展开失效
function rowKey(row: PersonaVote): string {
  return `${row.persona_id ?? 'p'}-${row.persona_name || row.name || ''}`
}

function fmt(v: unknown): string {
  return typeof v === 'number' ? v.toFixed(2) : '—'
}
function prefLabel(p: string): string {
  return { aggressive: '激进', neutral: '中性', conservative: '保守', custom: '自定义' }[p] || p
}
function prefType(p: string): 'danger' | 'success' | 'info' {
  return ({ aggressive: 'danger', neutral: 'info', conservative: 'success' } as const)[
    p as 'aggressive' | 'neutral' | 'conservative'
  ] || 'info'
}
</script>

<style scoped>
.expand-hint {
  display: inline-flex;
  vertical-align: middle;
  color: #a9aeb8;
  margin-right: 2px;
}
.pref-tag {
  margin-left: 6px;
  transform: scale(0.9);
}
.negative {
  color: #f53f3f;
  font-weight: 600;
}
.persona-detail {
  padding: 10px 16px 14px;
  background: #fafbfc;
}
.detail-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.detail-name {
  font-weight: 600;
  font-size: 13px;
}
.detail-weight {
  font-size: 12px;
  color: #8f959e;
}
.detail-opinion-title {
  margin: 8px 0 4px;
  font-size: 12px;
  font-weight: 600;
  color: #4e5969;
}
.detail-reasoning {
  font-size: 13px;
  line-height: 1.8;
  color: #1f2329;
  white-space: pre-wrap;
}
</style>
