#agent_core/risk_agent.py
"""
风险监控Agent（DeepSeek版）
职责：基于语义理解，判断决策中的清零风险、过载信号和ZOH适用性。

输入包含量化分析Agent的输出，作为风险评估的参考。
"""

import json
import re
from models.schemas import RiskResult, QuantResult
from agent_core.ai_client import chat

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

    # 尝试从回复中提取JSON
    try:
        clean_text = response_text.strip()
        if clean_text.startswith("```"):
            clean_text = re.sub(r'^```(?:json)?\s*', '', clean_text)
            clean_text = re.sub(r'\s*```$', '', clean_text)

        data = json.loads(clean_text)

        return RiskResult(
            risk_level=str(data["risk_level"]),
            bankruptcy_risk=bool(data["bankruptcy_risk"]),
            overload_signal=bool(data["overload_signal"]),
            zoh_recommend=bool(data["zoh_recommend"]),
            suggestion=str(data["suggestion"])
        )
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        return RiskResult(
            risk_level="低",
            bankruptcy_risk=False,
            overload_signal=False,
            zoh_recommend=False,
            suggestion=f"AI风险评估未能正确解析。\n错误: {str(e)}\n默认风险等级：低"
        )