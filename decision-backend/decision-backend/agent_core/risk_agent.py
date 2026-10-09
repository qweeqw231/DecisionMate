#agent_core/risk_agent.py
"""
风险监控Agent（DeepSeek版）
职责：基于语义理解，判断决策中的清零风险、过载信号和ZOH适用性。

输入包含量化分析Agent的输出，作为风险评估的参考。
"""

import logging

from models.schemas import RiskResult, QuantResult
from agent_core.ai_client import chat
from agent_core.json_utils import extract_json_object, as_bool

RISK_SYSTEM_PROMPT = """你是一个风险监控专家。你的任务是根据用户的决策场景和量化分析结果，评估其中的风险。

## 你的知识库（来自《个人决策支持系统：理论与实战全鉴》）

### 风险评估三维度

**1. 清零风险**
判断用户是否可能押上不可逆的核心资产（健康、学业根基、关键关系）。
触发信号：
- 涉及"全部"、"所有"、"退学"、"辞职"等不可逆行为
- 量化分析的f*接近1.0（满仓押注）
- 决策失败后果无法挽回
**清零风险的严格定义**
清零风险是指：决策失败会导致不可逆的核心资产损失（健康崩溃、退学、辞职、关键关系断裂）。
以下情况不属于清零风险：
- 时间有限的集中投入（如“花一个周末复盘”），即使效果不佳，损失也仅限于该时间段
- 量化分析已经判断为高胜率(p≥0.85)、高赔率(b≥10)的重注，这类决策是“精准下注”而非“盲目押注”
- 用户明确提到了具体目标和方法（如“密卷暴露了设计模式漏洞”），说明有清晰计划，不是盲目投入

判断清零风险时，必须结合量化分析的结果：
- 如果量化Agent判断p≥0.85且b≥10，且用户有具体执行计划，则清零风险为false
- 只有当决策涉及“退学”、“辞职”、“全部存款”、“不顾身体极限”等不可逆行为时，才判定为清零风险

**2. 过载信号**
判断用户的身体和情绪是否处于过载状态。
触发信号：
- 提到"累"、"困"、"焦虑"、"压力"、"撑不住"、"熬夜"、"通宵"
- 提到身体症状："溃疡"、"淋巴"、"头疼"
- 提到时间严重不足

**3. ZOH适用性**
判断是否处于异步等待状态（需要离散采样而非连续跟踪）。
触发信号：
- 提到"等结果"、"等通知"、"等审批"、"公布"、"出成绩"

### 参照案例
- 5月13日休整日：身体报警（口腔溃疡、淋巴肿大、极度困倦），主动休整规避破产风险
- 5月22日休息：漫无目的复习的赔率极低，选择休息保护状态
- 缓考审批等待：启用ZOH离散采样，设定固定采样节点，保护心理带宽

## 输出格式
你必须严格输出一个JSON对象，不要输出任何其他内容：

{
  "risk_level": "低",
  "bankruptcy_risk": false,
  "overload_signal": false,
  "zoh_recommend": false,
  "suggestion": "详细的风险评估说明和建议"
}

risk_level 只能是 "低"、"中"、"高" 之一。
"""

VALID_RISK_LEVELS = ("低", "中", "高")

# AI 输出必须包含的决策字段；缺任何一个都视为不可信，按保守降级处理
REQUIRED_FIELDS = ("risk_level", "bankruptcy_risk", "overload_signal", "zoh_recommend")


def _degraded_result(reason: str) -> RiskResult:
    """
    解析失败时的保守兜底结果（fail-safe）。

    宁可误报风险，也不能在守护者失明时宣布「一切安全」。
    """
    return RiskResult(
        risk_level="高",
        bankruptcy_risk=True,
        overload_signal=False,
        zoh_recommend=False,
        degraded=True,
        suggestion=(
            "⚠️ 风险评估未能正确解析，已按「生存优先」原则降级为保守结果："
            "本次不建议重注，请人工复核后再决定。\n" + reason
        ),
    )


def assess(scenario: str, quant_result: QuantResult) -> RiskResult:
    """
    使用DeepSeek进行语义级风险评估。
    """
    # 构建包含量化结果的完整输入
    user_message = f"""## 用户决策场景
{scenario}

## 量化分析结果
- 胜率 p = {quant_result.p}
- 败率 q = {quant_result.q}
- 赔率 b = {quant_result.b}
- 凯利最优下注比例 f* = {quant_result.f_star}
- 场景类型：{quant_result.scenario_type}

请基于以上信息进行风险评估。"""

    response_text = chat(
        system_prompt=RISK_SYSTEM_PROMPT,
        user_message=user_message,
        temperature=0.3,
        max_tokens=1024
    )

    # 解析 AI 输出。
    # 安全关键：任何异常或字段缺失都必须倒向「保守」，而不是「无风险」。
    # 旧实现失败时返回 risk_level="低" / bankruptcy_risk=False（fail-open），
    # 相当于在守护者失明时宣布「一切安全」，与架构的「生存优先硬约束」相反。
    try:
        data = extract_json_object(response_text)
    except Exception as e:  # noqa: BLE001 —— 解析异常不得向上抛
        logging.warning("[风险Agent] 输出无法解析，已降级为保守结果：%s", e)
        return _degraded_result(
            f"解析错误：{e}\nAI 原始输出片段：{str(response_text)[:200]!r}"
        )

    # 输出必须包含完整决策字段；缺字段说明模型没有遵守约定，结果同样不可信
    missing = [key for key in REQUIRED_FIELDS if key not in data]
    if missing:
        logging.warning("[风险Agent] 输出缺少必需字段 %s，已降级为保守结果", missing)
        return _degraded_result(f"AI 输出缺少必需字段：{missing}")

    raw_level = data.get("risk_level")
    risk_level = str(raw_level).strip() if raw_level else "高"
    if risk_level not in VALID_RISK_LEVELS:
        logging.warning("[风险Agent] 非法 risk_level=%r，按保守处理为「高」", risk_level)
        risk_level = "高"

    return RiskResult(
        risk_level=risk_level,
        # 无法识别时默认 True（倒向保守），且不再因为字符串 "false" 非空而误判为 True
        bankruptcy_risk=as_bool(data.get("bankruptcy_risk"), default=True),
        overload_signal=as_bool(data.get("overload_signal"), default=False),
        zoh_recommend=as_bool(data.get("zoh_recommend"), default=False),
        suggestion=str(data.get("suggestion") or "")
    )