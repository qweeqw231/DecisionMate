# models/schemas.py
from pydantic import BaseModel, Field, StringConstraints
from typing import Annotated, List, Literal, Optional

# ==========================================
# P2 新增：请求体的统一约束
#
# 此前这些字段都是裸 str / List[dict]：空白场景会一路送进大模型并落库，
# activated_personas 是未类型化的 dict，缺字段时在管线里抛 KeyError → 500。
# 现在统一在请求模型层约束，非法输入直接 422，管线里不再需要防御性取值。
# ==========================================

MAX_SCENARIO_LENGTH = 4000
MAX_TITLE_LENGTH = 200
MAX_NAME_LENGTH = 50
MAX_PRINCIPLE_LENGTH = 500
MAX_FEEDBACK_LENGTH = 2000
MAX_BASIS_LENGTH = 500

# 决策场景：去首尾空白、非空、限长
ScenarioText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_SCENARIO_LENGTH),
]
# 标题 / 名称
TitleText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_TITLE_LENGTH),
]
NameText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_NAME_LENGTH),
]
OptionalText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=MAX_PRINCIPLE_LENGTH)]


class DecisionRequest(BaseModel):
    """前端发来的决策请求"""
    scenario: ScenarioText


class ActivatedPersonaInput(BaseModel):
    """
    前端传入的「参与本次会商的某个分身」。

    P2 修复：原先是 Optional[List[dict]]，键名写错或缺字段时会在管线里
    抛 KeyError → 500；权重也没有上下界。现在强类型 + 范围校验。
    """
    persona_id: int
    normalized_weight: float = Field(ge=0.0, le=1.0)


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
    # P0 修复：AI 输出解析失败时置 True，表示本结果由保守降级产生，而非真实评估
    degraded: bool = False


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


class HistoryReference(BaseModel):
    """
    P1 新增：本次决策检索到的历史相似决策。

    后端一直会检索历史并把参数注入量化 Agent 的 Prompt，但结果从未回传，
    前端无从展示——Phase 3.3 验收标准里的「历史参考」区域因此不可达。
    这里把检索结果如实回传，让用户能看到系统到底参考了什么。
    """
    decision_id: int
    similarity: float
    scenario_type: Optional[str] = None
    p: Optional[float] = None
    b: Optional[float] = None
    f_star: Optional[float] = None


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
    # P0 新增：风险 Agent 输出不可信（解析失败/字段缺失/非法取值）时置 True，
    # 供前端区分「真实的清零风险」与「风险校验降级」，避免把降级当成真实评估
    risk_degraded: bool = False
    # P1 新增：本次检索到的历史相似决策（Phase 3.3 的「历史参考」展示）
    history_references: Optional[List[HistoryReference]] = None
    # P1-4 新增：关系边界的语义判定未能完成（本次「放行」不是因为确认不越界）
    boundary_check_degraded: bool = False


class FastDecisionReport(BaseModel):
    """快回路输出（无需量化分析和风险评估）"""
    loop_type: str = "fast"
    recommendation: str
    note: str = "此建议基于直觉和经验法则，未经过完整的量化分析。如需深度分析，请提供更多细节。"


# ==========================================
# P1-4 新增：关系边界（伦理关机）
# ==========================================

class BoundaryVerdict(BaseModel):
    """关系边界检查结论"""
    is_boundary: bool
    category: str = "none"        # hard_rule / semantic / none
    matched_rule: Optional[str] = None
    reason: str = ""
    # 语义判定调用失败时置 True：说明这次「放行」不是因为确实不越界，而是没查成
    degraded: bool = False


class BoundaryReport(BaseModel):
    """
    命中关系边界时的输出（架构 5.3.4）。

    这不是一次「分析结果」，而是系统主动关机：不做量化、不给建议，
    只把场景交还给用户的直觉与真诚。
    """
    loop_type: str = "boundary"
    shutdown_message: str
    reason: str
    category: str
    matched_rule: Optional[str] = None
    persisted: bool = False
    note: str = "此场景未被记录：消息、决策记录与向量库均未写入。"


# ==========================================
# P1-5 新增：L1 执行中校准
# ==========================================

class CalibrationResult(BaseModel):
    """一次执行中校准的结果（p、b 由模型重估，f* 由 kelly.py 确定性计算）"""
    p: float
    q: float
    b: float
    f_star: float          # 仲裁前
    verdict: str           # continue / watch / stop
    advice: str = ""
    reasoning: str = ""
    degraded: bool = False  # 模型输出不可用，已沿用上一次参数


class ExecutionUpdateRequest(BaseModel):
    """用户提交的一条阶段性进展"""
    note: str


class TrajectoryPoint(BaseModel):
    """轨迹上的一个点：初始预判，或一次执行中校准"""
    kind: str              # initial / calibration
    created_at: str
    p: float
    q: float
    b: float
    f_star: float              # 凯利原始值
    adjusted_f_star: float     # 经生存优先硬约束后的实际建议值
    advice: str
    verdict: str
    note: Optional[str] = None
    reasoning: str = ""
    risk_level: str = ""
    conflict: bool = False
    degraded: bool = False


class CalibrationTrajectory(BaseModel):
    """「初始预判 → 逐次校准」的完整轨迹（架构 6.2 要求对比展示）"""
    decision_id: int
    scenario: str
    scenario_type: str
    points: List[TrajectoryPoint]


# ==========================================
# Phase 3.2 新增：对话与消息模型
# ==========================================

class ConversationCreate(BaseModel):
    """创建对话的请求体"""
    title: Optional[TitleText] = None  # 可选标题，不传则自动生成


class ConversationUpdate(BaseModel):
    """更新对话的请求体（重命名）"""
    title: TitleText


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
    scenario: ScenarioText       # 用户输入的决策场景
    activated_personas: Optional[List[ActivatedPersonaInput]] = None  # Phase 4.2.3


# ==========================================
# Phase 3.3 新增：反馈、复盘、能力档案模型
# ==========================================

class FeedbackRequest(BaseModel):
    """用户提交的反馈"""
    # P2：枚举化，避免任意字符串被当作反馈类型写库并参与 L3 统计
    feedback_type: Literal["useful", "inaccurate", "custom"]
    feedback_text: Optional[str] = Field(default=None, max_length=MAX_FEEDBACK_LENGTH)


class NewFactorProposal(BaseModel):
    """新因子提议"""
    factor_name: str           # 如"抗压能力"
    suggested_value: float     # 建议初始值
    basis: str                 # 提议依据
    supporting_decisions: List[int] = []  # 支持此提议的决策记录ID列表
    data_insufficient: bool = False  # 数据是否不充分（<3条支持）


class AddFactorRequest(BaseModel):
    """
    新增能力因子的请求体（用户在复盘摘要卡片中确认后提交）。

    P0 修复：该端点原先用裸标量参数声明，FastAPI 会解析成 query string，
    而客户端（含鸿蒙前端）提交的是 JSON body，导致恒定 422，
    「新因子提议 → 用户接受」这条链路实际不可达。
    """
    # 名称与取值的校验统一由 factor_guard.validate_new_factor 负责（含保留名冲突），
    # 因此这里保持裸 str，避免同一字段的错误码被拆成 400/422 两种。
    factor_name: str
    value: float
    basis: Annotated[str, StringConstraints(strip_whitespace=True, max_length=MAX_BASIS_LENGTH)] = ""


class ArchiveReport(BaseModel):
    """复盘归档Agent输出的复盘报告"""
    decision_id: int            # 关联的决策记录ID
    initial_f_star: float       # 初始f*
    feedback_type: str          # 用户反馈类型
    deviation_analysis: str     # 偏差分析文字
    factor_updates: dict        # 能力因子变化（仅含实际写入的项），如 {"考试备战能力": {"old": 0.85, "new": 0.88}}
    new_factor_proposal: Optional[NewFactorProposal] = None
    reusable_pattern: Optional[str] = None  # 可复用模式提取
    # P0 修复：能力因子写入守卫的拒绝/钳制记录，便于排查「AI 提议了但没生效」的原因
    guard_rejections: List[str] = []


# ==========================================
# Phase 4.2 新增：分身模型
# ==========================================

class PersonaCreate(BaseModel):
    """创建自定义分身"""
    name: NameText
    risk_preference: Literal["aggressive", "neutral", "conservative", "custom"]
    core_principle: Optional[OptionalText] = None


class PersonaUpdate(BaseModel):
    """更新分身信息"""
    name: Optional[NameText] = None
    core_principle: Optional[OptionalText] = None
    weight: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    risk_preference: Optional[Literal["aggressive", "neutral", "conservative", "custom"]] = None


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