<template>
  <el-collapse v-model="opened" class="exec-collapse" @change="onToggle">
    <el-collapse-item name="l1">
      <template #title>
        <span class="collapse-title">
          <el-icon><TrendCharts /></el-icon>
          执行跟踪 · L1 校准
          <el-tag v-if="calibrationCount" size="small" effect="plain" class="count-tag">
            已校准 {{ calibrationCount }} 次
          </el-tag>
          <el-tag v-if="stopped" size="small" type="danger" effect="light" class="count-tag">
            已建议止损
          </el-tag>
        </span>
      </template>

      <div class="hint">
        决策在执行过程中出现阶段性结果时，在这里记录一条进展。
        系统会重新估算胜率与赔率、重算 f*，并按「生存优先硬约束」给出继续 / 观望 / 止损的建议。
      </div>

      <div class="input-row">
        <el-input
          v-model="note"
          type="textarea"
          :rows="2"
          maxlength="2000"
          show-word-limit
          placeholder="例：第一周完成了一半，比计划慢；关键资料已经拿到"
        />
        <el-button type="primary" :loading="submitting" @click="submit">记录进展</el-button>
      </div>

      <el-skeleton v-if="loading" :rows="3" animated />

      <el-alert v-else-if="error" type="error" :closable="false" :title="`加载失败：${error}`" />

      <el-table v-else-if="trajectory" :data="trajectory.points" size="small" class="trajectory-table">
        <el-table-column type="expand" width="40">
          <template #default="{ row }">
            <div class="detail">
              <div v-if="row.note" class="detail-row">
                <span class="detail-label">阶段性结果</span>
                <span class="detail-value">{{ row.note }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">系统建议</span>
                <span class="detail-value">{{ row.advice }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">分析说明</span>
                <span class="detail-value">{{ row.reasoning || '—' }}</span>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="100">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="阶段" width="80">
          <template #default="{ row }">
            <el-tag v-if="row.kind === 'initial'" size="small" effect="plain">初始预判</el-tag>
            <el-tag v-else size="small" type="info" effect="plain">校准</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="p" width="60">
          <template #default="{ row }">{{ row.p.toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="b" width="60">
          <template #default="{ row }">{{ row.b.toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="f*" width="110">
          <template #default="{ row }">
            <span>{{ row.adjusted_f_star.toFixed(2) }}</span>
            <span v-if="clampNote(row)" class="clamp">（原 {{ row.f_star.toFixed(2) }}）</span>
          </template>
        </el-table-column>
        <el-table-column label="变化" width="80">
          <template #default="{ row, $index }">
            <span v-if="$index === 0" class="muted">—</span>
            <span v-else :class="deltaClass(row, $index)">{{ deltaText(row, $index) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="执行判定" min-width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="verdictTagType(row.verdict)">{{ verdictLabel(row.verdict) }}</el-tag>
            <el-tooltip v-if="row.degraded" content="本次校准未能完成，已沿用上一次的参数" placement="top">
              <el-icon class="warn-icon"><WarningFilled /></el-icon>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>
    </el-collapse-item>
  </el-collapse>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { CalibrationTrajectory, TrajectoryPoint } from '../../types'
import { getExecutionTrajectory, addExecutionUpdate } from '../../api/decision'

const props = defineProps<{ convId: number; msgId: number }>()

const opened = ref<string[]>([])
const trajectory = ref<CalibrationTrajectory | null>(null)
const loading = ref(false)
const submitting = ref(false)
const error = ref('')
const note = ref('')

const calibrationCount = computed(() =>
  trajectory.value ? Math.max(trajectory.value.points.length - 1, 0) : 0,
)
const stopped = computed(
  () => trajectory.value?.points.some((p) => p.verdict === 'stop') ?? false,
)

const VERDICT_LABELS: Record<string, string> = {
  continue: '继续执行',
  watch: '观望',
  stop: '及时止损',
}
function verdictLabel(verdict: string): string {
  return VERDICT_LABELS[verdict] ?? verdict
}
function verdictTagType(verdict: string): 'success' | 'warning' | 'danger' | 'info' {
  return ({ continue: 'success', watch: 'warning', stop: 'danger' } as const)[
    verdict as 'continue' | 'watch' | 'stop'
  ] ?? 'info'
}

/** 实际建议值被生存优先硬约束下调过时，把原始值也显示出来 */
function clampNote(row: TrajectoryPoint): boolean {
  return Math.abs(row.adjusted_f_star - row.f_star) > 1e-6
}

function deltaText(row: TrajectoryPoint, index: number): string {
  const prev = trajectory.value?.points[index - 1]
  if (!prev) return '—'
  const diff = row.adjusted_f_star - prev.adjusted_f_star
  if (Math.abs(diff) < 1e-6) return '持平'
  return `${diff > 0 ? '↑' : '↓'} ${diff > 0 ? '+' : ''}${diff.toFixed(2)}`
}
function deltaClass(row: TrajectoryPoint, index: number): string {
  const prev = trajectory.value?.points[index - 1]
  if (!prev) return 'muted'
  const diff = row.adjusted_f_star - prev.adjusted_f_star
  if (Math.abs(diff) < 1e-6) return 'muted'
  return diff > 0 ? 'up' : 'down'
}

function fmtTime(iso: string): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso.slice(0, 16)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    trajectory.value = await getExecutionTrajectory(props.convId, props.msgId)
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}

function onToggle(value: string | string[]) {
  const isOpen = Array.isArray(value) ? value.includes('l1') : value === 'l1'
  if (isOpen && !trajectory.value && !loading.value) load()
}

async function submit() {
  const text = note.value.trim()
  if (!text) {
    ElMessage.warning('请先描述这条阶段性结果')
    return
  }
  submitting.value = true
  try {
    trajectory.value = await addExecutionUpdate(props.convId, props.msgId, text)
    note.value = ''
    const latest = trajectory.value.points[trajectory.value.points.length - 1]
    ElMessage.success(`已校准：${latest.advice}`)
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.exec-collapse {
  margin-top: 10px;
}
.collapse-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}
.count-tag {
  margin-left: 4px;
}
.hint {
  font-size: 12px;
  color: #8f959e;
  line-height: 1.7;
  margin-bottom: 10px;
}
.input-row {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  margin-bottom: 12px;
}
.trajectory-table {
  font-size: 12px;
}
.clamp {
  color: #e6a23c;
  font-size: 11px;
}
.up {
  color: #27ae60;
}
.down {
  color: #e74c3c;
}
.muted {
  color: #a0a4ab;
}
.warn-icon {
  color: #e6a23c;
  margin-left: 4px;
  vertical-align: -2px;
}
.detail {
  padding: 4px 10px;
  font-size: 12px;
}
.detail-row {
  display: flex;
  gap: 8px;
  margin-bottom: 4px;
  line-height: 1.7;
}
.detail-label {
  flex: none;
  width: 72px;
  color: #8f959e;
}
.detail-value {
  color: #4e5969;
  white-space: pre-wrap;
}
</style>
