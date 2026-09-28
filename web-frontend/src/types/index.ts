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
  persona_name: string
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
}

// 快回路报告
export interface FastDecisionReport {
  loop_type: 'fast' | string
  recommendation: string
  note?: string
}

export type AnyReport = DecisionReport | FastDecisionReport

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
  factor_updates: Record<string, { old: number; new: number }>
  new_factor_proposal?: NewFactorProposal | null
  reusable_pattern?: string | null
}

// SSE 阶段事件
export interface StageEvent {
  stage: 'start' | 'fast' | 'quant' | 'personas' | 'risk' | 'scene' | 'merge' | string
  names?: string[]
}
