#agent_core/archive_agent.py
"""
复盘归档Agent
被动触发：用户反馈后执行偏差分析，更新能力因子，生成复盘摘要，检测新因子。
"""

import json
import logging
from datetime import datetime

from models.schemas import ArchiveReport, NewFactorProposal
from agent_core.ai_client import chat
from agent_core.json_utils import extract_json_object
from factor_guard import sanitize_factor_updates
from vector_store import get_user_profile, update_user_profile

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


QUALITATIVE_SYSTEM_PROMPT = """你是一个复盘分析专家。本次复盘的是一次**快回路**决策——
系统当时只给了直觉建议，没有做量化分析，因此没有胜率 / 赔率 / f* 可供比对。

## 你的任务
1. **定性回顾**：结合用户的反馈，说明这次直觉建议是否贴合实际，以及可能的原因。
2. **可复用模式提取**：如果这次经验值得沉淀，用一句话总结。

## 约束
- **不要**提议能力因子调整：没有量化偏差作为依据，任何因子调整都是凭空猜测。
- 输出中的 factor_updates 必须是空对象，new_factor_proposal 必须是 null。

## 输出格式
你必须严格输出一个JSON对象：
{
  "deviation_analysis": "定性回顾文字",
  "factor_updates": {},
  "reusable_pattern": "可复用模式（可选，无则填null）",
  "new_factor_proposal": null
}
"""


def run_archive(decision_id: int, initial_f_star: float, p: float, q: float, b: float,
                scenario_type: str, feedback_type: str, feedback_text: str = "",
                params_available: bool = True) -> ArchiveReport:
    """
    执行复盘分析。

    params_available=False 表示这是一次快回路决策：没有量化参数可比对，
    因此只做定性复盘，不产生能力因子调整（凭空猜测的因子调整会污染能力档案）。
    """

    # 获取当前能力档案作为参考
    profile = get_user_profile()

    if params_available:
        system_prompt = ARCHIVE_SYSTEM_PROMPT
        params_block = f"""## 初始决策参数
- 胜率p = {p}
- 败率q = {q}
- 赔率b = {b}
- 凯利最优下注比例 f* = {initial_f_star}
- 场景类型：{scenario_type}
"""
    else:
        system_prompt = QUALITATIVE_SYSTEM_PROMPT
        params_block = """## 决策类型
快回路（直觉建议），没有量化参数可供比对。
"""

    user_message = f"""{params_block}
## 用户反馈
- 反馈类型：{feedback_type}
- 反馈文字：{feedback_text if feedback_text else "无"}

## 当前能力因子
{json.dumps(profile, ensure_ascii=False, indent=2)}
"""

    response_text = chat(
        system_prompt=system_prompt,
        user_message=user_message,
        temperature=0.3,
        max_tokens=1024
    )

    # 解析 AI 输出
    try:
        data = extract_json_object(response_text)

        # ---- 更新能力因子（P0 修复：所有写入都必须经过 factor_guard 校验）----
        raw_updates = data.get("factor_updates") or {}
        proposals: dict = {}
        reasons: dict = {}
        if isinstance(raw_updates, dict):
            for factor_name, update_info in raw_updates.items():
                if not isinstance(update_info, dict) or "new" not in update_info:
                    continue
                proposals[factor_name] = update_info["new"]
                reasons[factor_name] = update_info.get("reason", "复盘校准")

        accepted, rejections = sanitize_factor_updates(profile, proposals)
        if not params_available:
            # 快回路没有量化偏差作为依据，任何因子调整都是凭空猜测
            if accepted or proposals:
                rejections.append(
                    "本次为快回路决策，没有量化偏差依据，已跳过全部能力因子调整"
                )
            accepted = {}
        for reason in rejections:
            logging.warning("[复盘归档] 因子写入未通过校验：%s", reason)

        # P2 修复：逐个因子写入并各自兜错。
        # 原实现把所有写入放在同一个 try 里，写到一半失败会整体跳到 except，
        # 于是「已经写进去的因子」被上报成 factor_updates={} —— 报告少报了实际发生的事。
        applied_updates: dict = {}
        if accepted:
            now = datetime.now().isoformat()
            for factor_name, new_value in accepted.items():
                old_value = profile.get(factor_name)
                reason = reasons.get(factor_name, "复盘校准")
                try:
                    update_user_profile({
                        factor_name: new_value,
                        f"{factor_name}_updated_at": now,
                        f"{factor_name}_basis": reason,
                    })
                except Exception as e:  # noqa: BLE001
                    logging.error("[复盘归档] 写入因子「%s」失败：%s", factor_name, e)
                    rejections.append(f"「{factor_name}」写入失败：{e}")
                    continue
                applied_updates[factor_name] = {
                    "old": old_value,
                    "new": new_value,
                    "reason": reason,
                }

        # 解析新因子提议（快回路没有量化依据，不接收提议）
        new_factor = None
        if params_available and data.get("new_factor_proposal"):
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
            factor_updates=applied_updates,   # 只上报真正写入的值，不再是模型的原始提议
            new_factor_proposal=new_factor,
            reusable_pattern=data.get("reusable_pattern"),
            guard_rejections=rejections,
            params_available=params_available,
        )

    except Exception as e:  # noqa: BLE001 —— 复盘失败不应中断反馈流程
        logging.error("[复盘归档] 分析失败：%s", e)
        return ArchiveReport(
            decision_id=decision_id,
            initial_f_star=initial_f_star,
            feedback_type=feedback_type,
            deviation_analysis=f"复盘分析异常: {str(e)}",
            factor_updates={},
            new_factor_proposal=None,
            guard_rejections=[f"复盘分析异常：{e}"],
            params_available=params_available,
        )