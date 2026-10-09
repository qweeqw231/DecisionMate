// 镜像后端 models/schemas.py 的核心类型

export interface DecisionRequest {
  scenario: string
}

export interface QuantResult {
  p: number
  q: number
  b: number
  f_star: number
  scenario_type: string
  reasoning: string
}

export interface RiskResult {
  risk_level: string
  bankruptcy_risk: boolean
  overload_signal: boolean
  zoh_recommend: boolean
  suggestion: string
}

export interface StrategyItem {
  phase: string
  date_range: string
  strategy_name: string
  suggestion: string
  reference: string
}

export interface SceneResult {
  scene_recognized: boolean
  scene_type: string
  complex_type: string
  strategies: StrategyItem[]
  timeline_summary: string
  reasoning: string
}

export interface PersonaVote {
  persona_id?: number
  persona_name?: string
  /** 后端 pipeline 中实际返回的字段名 */
  name?: string
  risk_preference?: string
  weight: number
  p?: number
  q?: number
  b?: number
  f_star: number
  summary?: string
  reasoning?: string
}

// 慢回路报告（Mux 融合输出）
export interface HistoryReference {
  decision_id: number
  similarity: number
  scenario_type?: string | null
  p?: number | null
  b?: number | null
  f_star?: number | null
}

export interface DecisionReport {
  loop_type: 'slow' | string
  recommendation: string
  f_star: number
  risk_level: string
  scenario_type: string
  quant_opinion: string
  risk_opinion: string
  calculation_detail: string
  scene_result?: SceneResult | null
  persona_results?: PersonaVote[] | null
  conflict_detected?: boolean
  /** 风险 Agent 输出不可信（解析失败/字段缺失/非法取值），结论由保守降级产生 */
  risk_degraded?: boolean
  /** 本次检索到的历史相似决策（此前只注入 Prompt，用户看不到） */
  history_references?: HistoryReference[] | null
  /** 关系边界的语义判定未能完成：本次放行不是因为确认不越界 */
  boundary_check_degraded?: boolean
}

// 关系边界关机（架构 5.3.4）：不做量化，只把场景交还给用户
export interface BoundaryReport {
  loop_type: 'boundary'
  shutdown_message: string
  reason: string
  category: string
  matched_rule?: string | null
  persisted: boolean
  note: string
}

export interface BoundaryConfig {
  enabled: boolean
  use_semantic_check: boolean
  hard_patterns: string[]
  shutdown_message: string
  skip_persistence: boolean
}

export interface BoundaryConfigMeta {
  current: BoundaryConfig
  defaults: BoundaryConfig
  updated_at: string | null
}

// 快回路报告
export interface FastDecisionReport {
  loop_type: 'fast' | string
  recommendation: string
  note?: string
}

export type AnyReport = DecisionReport | FastDecisionReport | BoundaryReport

export interface Conversation {
  id: number
  title: string
  created_at: string
  updated_at: string
  message_count: number
  is_pinned: boolean
}

export interface Message {
  id: number
  conversation_id: number
  role: 'user' | 'assistant' | string
  content: string
  created_at: string
}

export interface ActivatedPersona {
  persona_id: number
  normalized_weight: number
}

export interface Persona {
  id: number
  name: string
  risk_preference: 'aggressive' | 'neutral' | 'conservative' | 'custom' | string
  core_principle: string
  system_prompt: string
  weight: number
  is_preset: boolean | number
  created_at: string
}

export interface PersonaCreatePayload {
  name: string
  risk_preference: string
  core_principle?: string
}

export interface PersonaUpdatePayload {
  name?: string
  core_principle?: string
  weight?: number
  risk_preference?: string
}

export interface NewFactorProposal {
  factor_name: string
  suggested_value: number
  basis: string
  supporting_decisions: number[]
  data_insufficient: boolean
}

export interface ArchiveReport {
  decision_id: number
  initial_f_star: number
  feedback_type: string
  deviation_analysis: string
  factor_updates: Record<string, { old: number | string; new: number }>
  new_factor_proposal?: NewFactorProposal | null
  reusable_pattern?: string | null
  /** 因子写入守卫的钳制/拒绝记录：解释「模型提议了但没生效」 */
  guard_rejections?: string[]
}

export interface AddFactorPayload {
  factor_name: string
  value: number
  basis?: string
}

// SSE 阶段事件
export interface StageEvent {
  stage: 'start' | 'fast' | 'quant' | 'personas' | 'risk' | 'scene' | 'merge' | string
  names?: string[]
}

// ---------- L3 系统自校正：汇总审计 ----------
export interface AuditTotals {
  decisions: number
  with_feedback: number
  useful: number
  inaccurate: number
  feedback_coverage: number | null
  reports_missing: number
  reports_unparseable: number
}

export interface AuditBreakdown {
  key: string
  decisions: number
  with_feedback: number
  useful: number
  inaccurate: number
  accuracy: number | null
  avg_f_star: number | null
  feedback_coverage: number | null
}

export interface AuditTrendPoint {
  month: string
  decisions: number
  with_feedback: number
  feedback_coverage: number | null
  accuracy: number | null
  heavy_bet_count: number
  heavy_bet_share: number | null
  avg_f_star: number | null
}

export interface AuditQuality {
  reports_usable: number
  scene_recognized_rate: number | null
  conflict_rate: number | null
  persona_conflict_count: number
  risk_degraded_rate: number | null
  survival_clamped_count: number
  survival_clamp_rate: number | null
  f_star_vs_pre_arbitration_deviations: number
  f_star_comparable: number
}

export interface ScenarioTypeVariants {
  normalized: string
  variants: string[]
  count: number
}

export interface SystemAudit {
  generated_at: string
  window: { start: string | null; end: string | null }
  totals: AuditTotals
  decision_accuracy: { value: number | null; sample: number }
  loop_distribution: Record<string, number>
  recommendation_mix: Record<string, number>
  recommendation_mix_ratio: Record<string, number>
  risk_level_distribution: Record<string, number>
  avg_f_star: number | null
  negative_f_star_share: number | null
  by_scenario_type: AuditBreakdown[]
  by_loop_type: AuditBreakdown[]
  trend_by_month: AuditTrendPoint[]
  quality: AuditQuality
  mux_parameters: Record<string, number>
  data_quality: { scenario_type_variants: ScenarioTypeVariants[] }
  capability_profile: Record<string, unknown>
  /** 关系边界配置（架构 6.4 的「用户可调整底层参数」） */
  boundary_config: BoundaryConfigMeta
  /** 数据能力边界：后端如实标注，前端必须原样展示 */
  limitations: string[]
}
