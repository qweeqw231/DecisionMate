#agent_core/archive_agent.py
"""
复盘归档Agent
被动触发：用户反馈后执行偏差分析，更新能力因子，生成复盘摘要，检测新因子。
"""

import json
from datetime import datetime
from typing import Optional
from models.schemas import ArchiveReport, NewFactorProposal
from agent_core.ai_client import chat
from vector_store import get_user_profile, update_user_profile, add_profile_factor

ARCHIVE_SYSTEM_PROMPT = """你是一个复盘分析专家。你的任务是对比用户的决策初始预判和实际结果，执行偏差分析。

## 输入信息
你会收到：
1. 初始决策参数：胜率p、败率q、赔率b、凯利最优下注比例f*、场景类型
2. 用户反馈：反馈类型（有用/不太准/自定义）和可选的文字描述

## 你的任务
1. **偏差分析**：对比初始f*和用户反馈，判断预判是否准确。分析可能的原因。
2. **能力因子更新建议**：根据偏差方向，建议调整哪些能力因子（考试备战能力、行政博弈能力、技术速通能力、风险偏好等），调整幅度控制在±0.05以内。
3. **可复用模式提取**：如果本次决策有值得记录的模式，用一句话总结。
4. **新因子检测**：如果发现现有能力因子无法解释的持续偏差（偏差≥20%），且至少有2-3个类似历史决策支持同一模式，生成新因子提议。如果没有足够数据支持，仍可提议但标注data_insufficient=true。

## 输出格式
你必须严格输出一个JSON对象：
{
  "deviation_analysis": "偏差分析文字",
  "factor_updates": {"因子名": {"old": 旧值, "new": 新值, "reason": "调整依据"}},
  "reusable_pattern": "可复用模式（可选，无则填null）",
  "new_factor_proposal": {
    "factor_name": "新因子名",
    "suggested_value": 0.80,
    "basis": "提议依据",
    "supporting_decisions": [1, 2, 3],
    "data_insufficient": false
  }  // 如果没有新因子提议，填null
}
"""


def run_archive(decision_id: int, initial_f_star: float, p: float, q: float, b: float,
                scenario_type: str, feedback_type: str, feedback_text: str = "") -> ArchiveReport:
    """执行复盘分析"""

    # 获取当前能力档案作为参考
    profile = get_user_profile()

    user_message = f"""## 初始决策参数
- 胜率p = {p}
- 败率q = {q}
- 赔率b = {b}
- 凯利最优下注比例 f* = {initial_f_star}
- 场景类型：{scenario_type}

## 用户反馈
- 反馈类型：{feedback_type}
- 反馈文字：{feedback_text if feedback_text else "无"}

## 当前能力因子
{json.dumps(profile, ensure_ascii=False, indent=2)}
"""

    response_text = chat(
        system_prompt=ARCHIVE_SYSTEM_PROMPT,
        user_message=user_message,
        temperature=0.3,
        max_tokens=1024
    )

    # 解析AI输出
    import re as re_module
    try:
        clean_text = response_text.strip()
        if clean_text.startswith("```"):
            clean_text = re_module.sub(r'^```(?:json)?\s*', '', clean_text)
            clean_text = re_module.sub(r'\s*```$', '', clean_text)
        data = json.loads(clean_text)

        # 更新能力因子
        factor_updates = data.get("factor_updates", {})
        for factor_name, update_info in factor_updates.items():
            if "new" in update_info:
                now = datetime.now().isoformat()
                reason = update_info.get("reason", "复盘校准")
                updates = {
                    factor_name: update_info["new"],
                    f"{factor_name}_updated_at": now,
                    f"{factor_name}_basis": reason
                }
                update_user_profile(updates)

        # 解析新因子提议
        new_factor = None
        if data.get("new_factor_proposal"):
            nfp = data["new_factor_proposal"]
            new_factor = NewFactorProposal(
                factor_name=nfp.get("factor_name", ""),
                suggested_value=nfp.get("suggested_value", 0.5),
                basis=nfp.get("basis", ""),
                supporting_decisions=nfp.get("supporting_decisions", []),
                data_insufficient=nfp.get("data_insufficient", False)
            )

        return ArchiveReport(
            decision_id=decision_id,
            initial_f_star=initial_f_star,
            feedback_type=feedback_type,
            deviation_analysis=data.get("deviation_analysis", ""),
            factor_updates=factor_updates,
            new_factor_proposal=new_factor,
            reusable_pattern=data.get("reusable_pattern")
        )

    except (json.JSONDecodeError, KeyError, ValueError) as e:
        return ArchiveReport(
            decision_id=decision_id,
            initial_f_star=initial_f_star,
            feedback_type=feedback_type,
            deviation_analysis=f"复盘分析异常: {str(e)}",
            factor_updates={},
            new_factor_proposal=None
        )