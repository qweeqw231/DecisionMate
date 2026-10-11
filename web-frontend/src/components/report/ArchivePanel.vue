<template>
  <div class="archive-panel">
    <el-divider content-position="left">
      <span class="archive-title">
        <el-icon><Files /></el-icon>
        复盘归档报告
      </span>
    </el-divider>

    <div class="archive-section">
      <template v-if="hasParams">
        <span class="label">初始 f*：</span>{{ report.initial_f_star.toFixed(2) }}
        <span class="label" style="margin-left: 16px">反馈类型：</span>
      </template>
      <template v-else>
        <span class="label">决策类型：</span>快回路（直觉建议）
        <span class="label" style="margin-left: 16px">反馈类型：</span>
      </template>
      <el-tag size="small" :type="feedbackTagType" effect="plain">{{ feedbackLabel }}</el-tag>
    </div>

    <div v-if="!hasParams" class="archive-section">
      <div class="sub-title">定性复盘</div>
      <el-alert
        type="info"
        :closable="false"
        class="qualitative-note"
        title="本次为快回路决策，没有胜率 / 赔率 / f* 可比对，因此只做定性回顾，不会调整能力因子。"
      />
    </div>

    <div class="archive-section">
      <div class="sub-title">偏差分析</div>
      <div class="text">{{ report.deviation_analysis }}</div>
    </div>

    <div v-if="factorEntries.length" class="archive-section">
      <div class="sub-title">能力因子更新</div>
      <div v-for="([name, change]) in factorEntries" :key="name" class="factor-row">
        <span class="factor-name">{{ name }}</span>
        <span class="factor-old">{{ fmtFactor(change.old) }}</span>
        <el-icon class="arrow"><Right /></el-icon>
        <span class="factor-new">{{ fmtFactor(change.new) }}</span>
      </div>
    </div>

    <!-- 写入守卫记录：解释「模型提议了但没生效」的原因 -->
    <div v-if="guardNotes.length" class="archive-section">
      <div class="sub-title">
        写入守卫记录
        <el-tooltip
          content="能力因子写入前会经过校验：只允许更新已有因子、必须是数值、钳制在 0~1、单次幅度不超过 ±0.05。以下是被钳制或拒绝的项。"
          placement="top"
        >
          <el-icon class="hint-icon"><QuestionFilled /></el-icon>
        </el-tooltip>
      </div>
      <ul class="guard-list">
        <li v-for="(note, index) in guardNotes" :key="index">{{ note }}</li>
      </ul>
    </div>

    <div v-if="report.new_factor_proposal" class="archive-section proposal">
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

      <div v-if="decision === ''" class="proposal-actions">
        <el-button
          size="small"
          type="primary"
          :loading="accepting"
          @click="acceptProposal"
        >
          接受提议
        </el-button>
        <el-button size="small" plain @click="decision = 'ignored'">忽略</el-button>
        <span class="proposal-hint">接受后该因子会写入能力档案，并参与后续决策</span>
      </div>
      <div v-else class="proposal-result">
        <el-tag v-if="decision === 'accepted'" size="small" type="success" effect="light">
          ✅ 已接受，新因子已写入能力档案
        </el-tag>
        <el-tag v-else size="small" type="info" effect="light">⏭️ 已忽略</el-tag>
      </div>
    </div>

    <div v-if="report.reusable_pattern" class="archive-section">
      <div class="sub-title">可复用模式</div>
      <div class="text">{{ report.reusable_pattern }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { ArchiveReport } from '../../types'
import { addUserFactor } from '../../api/decision'

const props = defineProps<{ report: ArchiveReport }>()

const decision = ref<'' | 'accepted' | 'ignored'>('')
const accepting = ref(false)

const factorEntries = computed(() => Object.entries(props.report.factor_updates || {}))
const guardNotes = computed(() => props.report.guard_rejections ?? [])
/** 快回路决策没有量化参数，复盘走定性路径 */
const hasParams = computed(() => props.report.params_available !== false)

const feedbackLabel = computed(() =>
  ({ useful: '决策有效', inaccurate: '决策不准确', custom: '自定义反馈' }[props.report.feedback_type]
    || props.report.feedback_type),
)
const feedbackTagType = computed<'success' | 'danger' | 'info'>(() =>
  ({ useful: 'success', inaccurate: 'danger', custom: 'info' } as const)[
    props.report.feedback_type as 'useful' | 'inaccurate' | 'custom'
  ] || 'info',
)

/** 因子值可能是历史脏数据（如字符串 "偏激进"），不能无条件 toFixed */
function fmtFactor(value: number | string): string {
  const num = Number(value)
  return Number.isFinite(num) ? num.toFixed(2) : String(value)
}

async function acceptProposal() {
  const proposal = props.report.new_factor_proposal
  if (!proposal) return

  accepting.value = true
  try {
    await addUserFactor({
      factor_name: proposal.factor_name,
      value: proposal.suggested_value,
      basis: proposal.basis,
    })
    decision.value = 'accepted'
    ElMessage.success(`已添加能力因子「${proposal.factor_name}」`)
  } catch (e) {
    // 失败不改变状态，允许用户重试
    ElMessage.error((e as Error).message)
  } finally {
    accepting.value = false
  }
}
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
.hint-icon {
  color: #a0a4ab;
  cursor: help;
  vertical-align: -2px;
}
.qualitative-note {
  margin-top: 4px;
  line-height: 1.7;
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
.guard-list {
  margin: 0;
  padding-left: 18px;
  color: #8f959e;
  font-size: 12px;
  line-height: 1.7;
}
.proposal {
  border-left: 3px solid #e6a23c;
  padding-left: 10px;
}
.proposal-actions {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.proposal-hint {
  font-size: 12px;
  color: #a0a4ab;
}
.proposal-result {
  margin-top: 8px;
}
</style>
