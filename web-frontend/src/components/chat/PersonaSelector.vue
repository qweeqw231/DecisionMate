<template>
  <el-popover
    :width="340"
    trigger="click"
    placement="top-start"
    popper-class="persona-selector-popover"
    @show="onShow"
  >
    <template #reference>
      <el-button :disabled="disabled" size="large" text>
        <el-icon><Avatar /></el-icon>
        <span class="selector-label">
          分身{{ personaStore.selectedIds.length ? `（${personaStore.selectedIds.length}）` : '' }}
        </span>
      </el-button>
    </template>

    <div class="selector-body">
      <div class="selector-tip">选择参与会商的分身并调整权重，发送时自动归一化</div>
      <div v-for="p in personaStore.personas" :key="p.id" class="persona-row">
        <el-checkbox
          :model-value="personaStore.selectedIds.includes(p.id)"
          @change="personaStore.togglePersona(p.id)"
        >
          <span class="persona-name">{{ p.name }}</span>
          <el-tag size="small" effect="plain" :type="prefType(p.risk_preference)" class="pref-tag">
            {{ prefLabel(p.risk_preference) }}
          </el-tag>
        </el-checkbox>
        <el-slider
          v-if="personaStore.selectedIds.includes(p.id)"
          :model-value="personaStore.weights[p.id] ?? p.weight"
          @update:model-value="(v: number) => personaStore.setWeight(p.id, v)"
          :min="0"
          :max="1"
          :step="0.05"
          :show-tooltip="false"
          class="weight-slider"
        />
      </div>
      <div class="weight-sum">权重总和：{{ personaStore.weightSum.toFixed(2) }}（发送时归一化）</div>
    </div>

    <template #footer>
      <el-button size="small" @click="onConfirm">保存选择</el-button>
    </template>
  </el-popover>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { usePersonaStore } from '../../stores/persona'
import { useConversationStore } from '../../stores/conversation'

withDefaults(defineProps<{ disabled?: boolean }>(), { disabled: false })

const personaStore = usePersonaStore()
const conversationStore = useConversationStore()

function onShow() {
  // 滑块值同步为最新分身权重
  personaStore.selectedIds.forEach((id) => {
    const p = personaStore.personas.find((x) => x.id === id)
    if (p && personaStore.weights[id] === undefined) personaStore.setWeight(id, p.weight)
  })
}

async function onConfirm() {
  if (!personaStore.selectedIds.length) {
    ElMessage.warning('请至少选择一个分身')
    return
  }
  if (conversationStore.activeId) {
    await personaStore.persistForConversation(conversationStore.activeId)
  }
  ElMessage.success('分身选择已保存')
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
.selector-label {
  margin-left: 4px;
  font-size: 14px;
}
.selector-tip {
  font-size: 12px;
  color: #8f959e;
  margin-bottom: 10px;
}
.persona-row {
  margin-bottom: 10px;
}
.persona-name {
  font-size: 13px;
}
.pref-tag {
  margin-left: 6px;
  transform: scale(0.9);
}
.weight-slider {
  margin: 2px 0 0 24px;
}
.weight-sum {
  font-size: 12px;
  color: #8f959e;
  text-align: right;
}
</style>
