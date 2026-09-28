<template>
  <el-table :data="votes" size="small" border class="vote-table">
    <el-table-column label="分身" min-width="110">
      <template #default="{ row }">
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
    <el-table-column label="p（胜率）" prop="p" width="82" align="center">
      <template #default="{ row }">{{ fmt(row.p) }}</template>
    </el-table-column>
    <el-table-column label="b（赔率）" prop="b" width="82" align="center">
      <template #default="{ row }">{{ fmt(row.b) }}</template>
    </el-table-column>
    <el-table-column label="f*（凯利值）" width="96" align="center">
      <template #default="{ row }">
        <span :class="{ negative: row.f_star < 0 }">{{ fmt(row.f_star) }}</span>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import type { PersonaVote } from '../../types'

defineProps<{ votes: PersonaVote[] }>()

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
.pref-tag {
  margin-left: 6px;
  transform: scale(0.9);
}
.negative {
  color: #f53f3f;
  font-weight: 600;
}
</style>
