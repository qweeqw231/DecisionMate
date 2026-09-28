# models/schemas.py
from pydantic import BaseModel
from typing import Optional,List


class DecisionRequest(BaseModel):
    """前端发来的决策请求"""
    scenario: str


class QuantResult(BaseModel):
    """量化分析Agent的输出"""
    p: float
    q: float
    b: float
    f_star: float
    scenario_type: str
    reasoning: str


class RiskResult(BaseModel):
    """风险监控Agent的输出"""
    risk_level: str
    bankruptcy_risk: bool
    overload_signal: bool
    zoh_recommend: bool
    suggestion: str


class StrategyItem(BaseModel):
    """单条策略"""
    phase: str          # 阶段名称，如"考前保留期"
    date_range: str     # 时间范围，如"5月22日-23日"
    strategy_name: str  # 策略名称，如"考前保留策略"
    suggestion: str     # 具体建议
    reference: str      # 参考案例（来自《全鉴》）


class SceneResult(BaseModel):
    """场景策略Agent的输出"""
    scene_recognized: bool              # 是否成功识别场景
    scene_type: str                     # 场景类型：考试复合体 / 通用场景
    complex_type: str                   # 复合体类型：天级/周级/学期级
    strategies: List[StrategyItem]      # 策略列表
    timeline_summary: str               # 时间线摘要
    reasoning: str                      # 推理过程


#phase 4.2 新增：
class PersonaVote(BaseModel):
    """单个分身的投票概览"""
    persona_name: str
    f_star: float
    weight: float
    summary: str


class DecisionReport(BaseModel):
    """Mux融合后的最终决策建议（慢回路）"""
    loop_type: str = "slow"        # 新增：标识回路类型
    recommendation: str
    f_star: float
    risk_level: str
    scenario_type: str
    quant_opinion: str
    risk_opinion: str
    calculation_detail: str
    scene_result: Optional[SceneResult] = None  # 新增：场景策略结果
    persona_results: Optional[List[dict]] = None  # Phase 4.2 新增：各分身原始结果
    conflict_detected: bool = False               # Phase 4.2 新增：是否检测到分身意见分歧


class FastDecisionReport(BaseModel):
    """快回路输出（无需量化分析和风险评估）"""
    loop_type: str = "fast"
    recommendation: str
    note: str = "此建议基于直觉和经验法则，未经过完整的量化分析。如需深度分析，请提供更多细节。"


# ==========================================
# Phase 3.2 新增：对话与消息模型
# ==========================================

class ConversationCreate(BaseModel):
    """创建对话的请求体"""
    title: Optional[str] = None  # 可选标题，不传则自动生成


class ConversationUpdate(BaseModel):
    """更新对话的请求体（重命名）"""
    title: str


class ConversationResponse(BaseModel):
    """对话列表中的单个对话"""
    id: int
    title: str
    created_at: str
    updated_at: str
    message_count: int  # 该对话中的消息数量
    is_pinned: bool     # 是否置顶


class MessageResponse(BaseModel):
    """单条消息"""
    id: int
    conversation_id: int
    role: str           # "user" 或 "assistant"
    content: str        # 用户输入或系统输出的完整报告 JSON 字符串
    created_at: str


class MessageCreate(BaseModel):
    """发送消息的请求体"""
    scenario: str       # 用户输入的决策场景
    activated_personas: Optional[List[dict]] = None  # Phase 4.2.3：[{persona_id, normalized_weight}]


# ==========================================
# Phase 3.3 新增：反馈、复盘、能力档案模型
# ==========================================

class FeedbackRequest(BaseModel):
    """用户提交的反馈"""
    feedback_type: str  # "useful" | "inaccurate" | "custom"
    feedback_text: Optional[str] = None  # 自定义文字（可选）


class NewFactorProposal(BaseModel):
    """新因子提议"""
    factor_name: str           # 如"抗压能力"
    suggested_value: float     # 建议初始值
    basis: str                 # 提议依据
    supporting_decisions: List[int] = []  # 支持此提议的决策记录ID列表
    data_insufficient: bool = False  # 数据是否不充分（<3条支持）


class ArchiveReport(BaseModel):
    """复盘归档Agent输出的复盘报告"""
    decision_id: int            # 关联的决策记录ID
    initial_f_star: float       # 初始f*
    feedback_type: str          # 用户反馈类型
    deviation_analysis: str     # 偏差分析文字
    factor_updates: dict        # 能力因子变化，如 {"考试备战能力": {"old": 0.85, "new": 0.88}}
    new_factor_proposal: Optional[NewFactorProposal] = None
    reusable_pattern: Optional[str] = None  # 可复用模式提取


# ==========================================
# Phase 4.2 新增：分身模型
# ==========================================

class PersonaCreate(BaseModel):
    """创建自定义分身"""
    name: str
    risk_preference: str  # aggressive / neutral / conservative / custom
    core_principle: Optional[str] = None


class PersonaUpdate(BaseModel):
    """更新分身信息"""
    name: Optional[str] = None
    core_principle: Optional[str] = None
    weight: Optional[float] = None
    risk_preference: Optional[str] = None  # 新增


class PersonaResponse(BaseModel):
    """分身信息响应"""
    id: int
    name: str
    risk_preference: str
    core_principle: str
    system_prompt: str
    weight: float
    is_preset: bool
    created_at: str

class ConversationPersonasUpdate(BaseModel):
    """更新对话分身选择的请求体"""
    persona_ids: List[int]