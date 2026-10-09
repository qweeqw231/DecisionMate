<template>
  <div class="audit-view">
    <div class="page-header">
      <el-button text @click="router.push('/')">
        <el-icon><ArrowLeft /></el-icon>&nbsp;返回
      </el-button>
      <span class="page-title">系统自省（L3）</span>
      <el-button text class="refresh-btn" :loading="loading" @click="load">
        <el-icon><Refresh /></el-icon>&nbsp;刷新
      </el-button>
    </div>

    <div class="page-body">
      <el-alert type="info" :closable="false" class="intro-alert">
        <template #title>
          这里是 L3 系统自校正：汇总系统运行以来的决策数据，供你判断系统是否存在<b>系统性偏差</b>。
          本页只读，不会修改任何数据、也不会调用大模型。
        </template>
      </el-alert>

      <el-skeleton v-if="loading && !audit" :rows="8" animated />

      <el-alert v-else-if="error" type="error" :closable="false" :title="`加载失败：${error}`" />

      <template v-else-if="audit">
        <!-- 概览 -->
        <el-card shadow="never" class="card">
          <template #header><span class="card-title">概览</span></template>
          <div class="window-line">
            统计窗口：{{ fmtTime(audit.window.start) }} → {{ fmtTime(audit.window.end) }}
            <span class="muted">（生成于 {{ fmtTime(audit.generated_at) }}）</span>
          </div>
          <div class="metrics">
            <div class="metric">
              <div class="metric-value">{{ audit.totals.decisions }}</div>
              <div class="metric-label">决策总数</div>
            </div>
            <div class="metric">
              <div class="metric-value">{{ pct(audit.totals.feedback_coverage) }}</div>
              <div class="metric-label">反馈覆盖率（{{ audit.totals.with_feedback }} 条）</div>
            </div>
            <div class="metric">
              <div class="metric-value" :class="accuracyClass">
                {{ pct(audit.decision_accuracy.value) }}
              </div>
              <div class="metric-label">决策级准确率（n={{ audit.decision_accuracy.sample }}）</div>
            </div>
            <div class="metric">
              <div class="metric-value">{{ num(audit.avg_f_star) }}</div>
              <div class="metric-label">平均 f*</div>
            </div>
          </div>
          <div class="sub-metrics">
            <span>反馈构成：有效 {{ audit.totals.useful }} / 不准确 {{ audit.totals.inaccurate }}</span>
            <span>负 f* 占比：{{ pct(audit.negative_f_star_share) }}</span>
            <span>可用报告：{{ audit.quality.reports_usable }} / {{ audit.totals.decisions }}</span>
          </div>
        </el-card>

        <!-- 建议档位分布 -->
        <el-card shadow="never" class="card">
          <template #header>
            <span class="card-title">建议档位分布</span>
            <span class="card-hint">系统给出「重注」的比例越高，越值得警惕是否偏激进</span>
          </template>
          <div v-for="band in bandRows" :key="band.key" class="bar-row">
            <span class="bar-label">{{ band.key }}</span>
            <div class="bar-track">
              <div
                class="bar-fill"
                :class="{ 'bar-warn': band.key === '重注' }"
                :style="{ width: barWidth(band.ratio) }"
              />
            </div>
            <span class="bar-value">{{ band.count }}（{{ pct(band.ratio) }}）</span>
          </div>
        </el-card>

        <!-- 月度趋势 -->
        <el-card shadow="never" class="card">
          <template #header><span class="card-title">月度趋势</span></template>
          <el-table v-if="audit.trend_by_month.length" :data="audit.trend_by_month" size="small" stripe>
            <el-table-column prop="month" label="月份" width="100" />
            <el-table-column prop="decisions" label="决策" width="70" />
            <el-table-column prop="with_feedback" label="反馈" width="70" />
            <el-table-column label="准确率" width="90">
              <template #default="{ row }">{{ pct(row.accuracy) }}</template>
            </el-table-column>
            <el-table-column label="重注占比" width="100">
              <template #default="{ row }">{{ pct(row.heavy_bet_share) }}</template>
            </el-table-column>
            <el-table-column label="平均 f*">
              <template #default="{ row }">{{ num(row.avg_f_star) }}</template>
            </el-table-column>
          </el-table>
          <el-empty v-else description="暂无数据" :image-size="60" />
        </el-card>

        <!-- 按场景拆分 -->
        <el-card shadow="never" class="card">
          <template #header>
            <span class="card-title">按场景类型拆分</span>
            <span class="card-hint">场景类型由模型自由生成，是「哪个 Agent 主导」的代理指标</span>
          </template>
          <el-table :data="audit.by_scenario_type" size="small" stripe>
            <el-table-column prop="key" label="场景类型" min-width="180" show-overflow-tooltip />
            <el-table-column prop="decisions" label="决策" width="70" />
            <el-table-column prop="with_feedback" label="反馈" width="70" />
            <el-table-column label="准确率" width="90">
              <template #default="{ row }">{{ pct(row.accuracy) }}</template>
            </el-table-column>
            <el-table-column label="平均 f*" width="90">
              <template #default="{ row }">{{ num(row.avg_f_star) }}</template>
            </el-table-column>
          </el-table>
          <div class="table-note">样本量小的分组（如反馈 &lt; 5 条）暂不足以说明问题。</div>
        </el-card>

        <!-- 质量信号 -->
        <el-card shadow="never" class="card">
          <template #header><span class="card-title">质量信号</span></template>
          <div class="kv-grid">
            <div v-for="item in qualityRows" :key="item.label" class="kv">
              <span class="kv-label">{{ item.label }}</span>
              <span class="kv-value">{{ item.value }}</span>
            </div>
          </div>
          <div class="param-line">
            <span class="muted">当前 Mux 参数（只读）：</span>
            <el-tag
              v-for="(value, key) in audit.mux_parameters"
              :key="key"
              size="small"
              effect="plain"
              class="param-tag"
            >
              {{ paramLabel(String(key)) }} = {{ value }}
            </el-tag>
          </div>
        </el-card>

        <!-- 能力画像 -->
        <el-card shadow="never" class="card">
          <template #header>
            <span class="card-title">能力画像</span>
            <span class="card-hint">这些因子会被注入各分身的 Prompt，直接影响参数估算</span>
          </template>
          <div v-if="profileRows.length" class="kv-grid">
            <div v-for="item in profileRows" :key="item.label" class="kv">
              <span class="kv-label">{{ item.label }}</span>
              <span class="kv-value">{{ item.value }}</span>
            </div>
          </div>
          <el-empty v-else description="未能读取能力画像（向量库不可用）" :image-size="60" />
        </el-card>

        <!-- 数据质量 -->
        <el-card v-if="audit.data_quality.scenario_type_variants.length" shadow="never" class="card">
          <template #header><span class="card-title">数据质量告警</span></template>
          <div
            v-for="variant in audit.data_quality.scenario_type_variants"
            :key="variant.normalized"
            class="variant-row"
          >
            同一场景被写成 {{ variant.count }} 个标签，会稀释按场景分组的统计：
            <el-tag
              v-for="label in variant.variants"
              :key="label"
              size="small"
              type="warning"
              effect="plain"
              class="variant-tag"
            >
              {{ label }}
            </el-tag>
          </div>
        </el-card>

        <!-- 能力边界：必须原样展示，避免误读 -->
        <el-card shadow="never" class="card limitations-card">
          <template #header>
            <span class="card-title">数据能力边界</span>
            <span class="card-hint">以下限制由后端随数据返回，请勿把决策级数字当成 Agent 级结论</span>
          </template>
          <ol class="limitations">
            <li v-for="(note, index) in audit.limitations" :key="index">{{ note }}</li>
          </ol>
        </el-card>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getSystemAudit } from '../api/decision'
import type { SystemAudit } from '../types'

const router = useRouter()
const audit = ref<SystemAudit | null>(null)
const loading = ref(false)
const error = ref('')

/** 建议档位的固定展示顺序 */
const BAND_ORDER = ['重注', '适度投入', '观望或小注', '做空/撤出', '未知']

const bandRows = computed(() => {
  const mix = audit.value?.recommendation_mix ?? {}
  const ratios = audit.value?.recommendation_mix_ratio ?? {}
  return BAND_ORDER.filter((key) => mix[key] !== undefined).map((key) => ({
    key,
    count: mix[key],
    ratio: ratios[key] ?? null,
  }))
})

const accuracyClass = computed(() => {
  const value = audit.value?.decision_accuracy.value
  if (value === null || value === undefined) return ''
  if (value < 0.6) return 'value-bad'
  if (value < 0.75) return 'value-warn'
  return 'value-good'
})

const QUALITY_LABELS: Record<string, string> = {
  scene_recognized_rate: '场景识别率',
  conflict_rate: '决策冲突率',
  persona_conflict_count: '分身意见分歧次数',
  risk_degraded_rate: '风险校验降级率',
  survival_clamp_rate: '生存优先降仓率',
}

const qualityRows = computed(() => {
  const quality = audit.value?.quality
  if (!quality) return []
  return Object.entries(QUALITY_LABELS).map(([key, label]) => {
    const raw = (quality as unknown as Record<string, number | null>)[key]
    const value = key.endsWith('_rate') ? pct(raw) : String(raw ?? '—')
    return { label, value }
  })
})

const profileRows = computed(() => {
  const profile = audit.value?.capability_profile ?? {}
  return Object.entries(profile)
    .filter(([key]) => !key.endsWith('_basis') && !key.endsWith('_updated_at') && key !== 'user_id')
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([label, value]) => ({ label, value: String(value) }))
})

const PARAM_LABELS: Record<string, string> = {
  heavy_bet_threshold: '重注阈值',
  survival_clamp_factor: '生存降仓系数',
  persona_conflict_threshold: '分身分歧阈值',
}
function paramLabel(key: string): string {
  return PARAM_LABELS[key] ?? key
}

function pct(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return `${(value * 100).toFixed(1)}%`
}
function num(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return value.toFixed(3)
}
function barWidth(ratio: number | null): string {
  if (!ratio) return '0%'
  return `${Math.max(ratio * 100, 1.5).toFixed(1)}%`
}
function fmtTime(value: string | null | undefined): string {
  if (!value) return '—'
  return value.replace('T', ' ').slice(0, 19)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    audit.value = await getSystemAudit()
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.audit-view {
  height: 100%;
  overflow-y: auto;
  background: #f5f6f7;
}
.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 24px;
  background: #fff;
  border-bottom: 1px solid #eef0f2;
  position: sticky;
  top: 0;
  z-index: 10;
}
.page-title {
  font-size: 16px;
  font-weight: 600;
}
.refresh-btn {
  margin-left: auto;
}
.page-body {
  max-width: 900px;
  margin: 20px auto;
  padding: 0 24px 40px;
}
.intro-alert {
  margin-bottom: 16px;
  line-height: 1.7;
}
.card {
  margin-bottom: 16px;
  border-radius: 10px;
}
.card-title {
  font-weight: 600;
}
.card-hint {
  margin-left: 10px;
  font-size: 12px;
  color: #a0a4ab;
}
.window-line {
  font-size: 13px;
  color: #4e5969;
  margin-bottom: 14px;
}
.muted {
  color: #a0a4ab;
}
.metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
}
.metric {
  background: #f7f8fa;
  border-radius: 8px;
  padding: 14px 16px;
}
.metric-value {
  font-size: 24px;
  font-weight: 600;
  color: #1d2129;
}
.value-good {
  color: #27ae60;
}
.value-warn {
  color: #f39c12;
}
.value-bad {
  color: #e74c3c;
}
.metric-label {
  margin-top: 4px;
  font-size: 12px;
  color: #8f959e;
}
.sub-metrics {
  margin-top: 14px;
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
  font-size: 12px;
  color: #8f959e;
}
.bar-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}
.bar-label {
  width: 96px;
  flex: none;
  font-size: 13px;
  color: #4e5969;
}
.bar-track {
  flex: 1;
  height: 14px;
  background: #f0f1f3;
  border-radius: 7px;
  overflow: hidden;
}
.bar-fill {
  height: 100%;
  background: #3498db;
  border-radius: 7px;
  transition: width 0.3s;
}
.bar-warn {
  background: #e67e22;
}
.bar-value {
  width: 130px;
  flex: none;
  text-align: right;
  font-size: 12px;
  color: #8f959e;
}
.table-note {
  margin-top: 8px;
  font-size: 12px;
  color: #a0a4ab;
}
.kv-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 10px 20px;
}
.kv {
  display: flex;
  justify-content: space-between;
  border-bottom: 1px dashed #eef0f2;
  padding: 6px 0;
  font-size: 13px;
}
.kv-label {
  color: #4e5969;
}
.kv-value {
  font-weight: 600;
  color: #1d2129;
}
.param-line {
  margin-top: 14px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
.param-tag {
  font-family: ui-monospace, Consolas, monospace;
}
.variant-row {
  font-size: 13px;
  color: #4e5969;
  line-height: 2;
}
.variant-tag {
  margin-left: 6px;
}
.limitations-card {
  border-left: 3px solid #f39c12;
}
.limitations {
  margin: 0;
  padding-left: 20px;
  font-size: 13px;
  color: #4e5969;
  line-height: 1.9;
}
</style>
