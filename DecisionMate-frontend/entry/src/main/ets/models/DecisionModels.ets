//src/main/ets/models/DecisionModels.ets
export class DecisionReport {
  recommendation: string = '';
  f_star: number = 0;
  risk_level: string = '';
  scenario_type: string = '';
  quant_opinion: string = '';
  risk_opinion: string = '';
  calculation_detail: string = '';
  scene_result: SceneResult | null = null;  // Phase 2 新增
  persona_results: PersonaResult[] = [];
  conflict_detected: boolean = false;
}

export class DecisionRequest {
  scenario: string = '';
}

export class StrategyItem {
  phase: string = '';
  date_range: string = '';
  strategy_name: string = '';
  suggestion: string = '';
  reference: string = '';
}

export class SceneResult {
  scene_recognized: boolean = false;
  scene_type: string = '';
  complex_type: string = '';
  strategies: StrategyItem[] = [];
  timeline_summary: string = '';
  reasoning: string = '';
}

// ==========================================
// Phase 3.2 新增：对话与消息模型
// ==========================================

export class ConversationItem {
  id: number = 0;
  title: string = '';
  created_at: string = '';
  updated_at: string = '';
  message_count: number = 0;
  is_pinned: boolean = false;
}

export class MessageItem {
  id: number = 0;
  conversation_id: number = 0;
  role: string = '';        // "user" 或 "assistant"
  content: string = '';     // 用户输入文本 或 系统报告JSON字符串
  created_at: string = '';
}


// ==========================================
// Phase 3.3 新增：复盘与新因子模型
// ==========================================
// 定义能力因子更新的结构
export interface FactorUpdate {
  old: number;
  new: number;
  reason?: string;
}


export class ArchiveReport {
  decision_id: number = 0;
  initial_f_star: number = 0;
  feedback_type: string = '';
  deviation_analysis: string = '';
  factor_updates: Record<string, FactorUpdate> = {};
  new_factor_proposal: NewFactorProposal | null = null;
  reusable_pattern: string = '';
}

export class NewFactorProposal {
  factor_name: string = '';
  suggested_value: number = 0;
  basis: string = '';
  supporting_decisions: number[] = [];
  data_insufficient: boolean = false;
  status: string = 'pending';  // 'pending' | 'accepted' | 'ignored'
}


// ==========================================
// Phase 4.2.1 新增：分身模型
// ==========================================

export class PersonaItem {
  id: number = 0;
  name: string = '';
  risk_preference: string = '';
  core_principle: string = '';
  system_prompt: string = '';
  weight: number = 0;
  is_preset: boolean = false;
  created_at: string = '';
}


// Phase 4.2.2 新增：分身投票概览
export class PersonaVote {
  persona_name: string = '';
  f_star: number = 0;
  weight: number = 0;
  summary: string = '';
}


export class PersonaResult {
  persona_id: number = 0;
  name: string = '';
  risk_preference: string = '';
  weight: number = 0;
  p: number = 0;
  q: number = 0;
  b: number = 0;
  f_star: number = 0;
  reasoning: string = '';
}


// 在 MessageItem 或单独定义
export class ActivatedPersona {
  persona_id: number = 0;
  normalized_weight: number = 0;
}