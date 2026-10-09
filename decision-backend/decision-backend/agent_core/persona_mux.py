#agent_core/persona_mux.py
"""
多分身融合器（Persona Mux）
职责：加权融合多个分身的独立分析结果，生成会商摘要。

P0 修复说明
-----------
1. 原先本函数只接收 risk_level（字符串），把风险 Agent 的 bankruptcy_risk 和
   suggestion 全部丢弃 —— 于是 mux.py 中的「生存优先硬约束」在多分身主链路上
   从未执行。现在改为接收完整的 RiskResult，并复用 mux.apply_survival_constraint()。
2. risk_opinion 原先是一句写死的「风险等级：X（基于中性分身评估）」，现在回填
   风险 Agent 的真实评估与建议。
3. scenario_type 由调用方传入中性分身的实际场景类型（原先恒为空字符串）。
"""

from typing import List

from models.schemas import DecisionReport, PersonaVote, RiskResult
from agent_core.mux import apply_survival_constraint, degraded_note, risk_advisory

# 分身意见分歧阈值：任意两个分身的 f* 差异超过该值即标记冲突
PERSONA_CONFLICT_THRESHOLD = 0.4


def merge_personas(persona_results: List[dict], weighted_f_star: float,
                   risk_result: RiskResult, scenario_type: str,
                   scene_result=None) -> DecisionReport:
    """
    融合多分身分析结果。

    参数:
        persona_results: 各分身的分析结果列表，每项包含 name, p, q, b, f_star,
                         reasoning, weight, scenario_type
        weighted_f_star: 加权后的 f*
        risk_result:     风险监控 Agent 的输出（含 bankruptcy_risk / suggestion）
        scenario_type:   场景类型（取中性分身的实际识别结果）
        scene_result:    场景策略结果

    返回:
        DecisionReport: 会商摘要 + 各分身投票概览 + 综合建议
    """
    # ---- 生存优先硬约束（与单分身链路共用同一实现）----
    adjusted_f_star, survival_conflict, survival_note = apply_survival_constraint(
        weighted_f_star, risk_result
    )

    # ---- 综合建议生成 ----
    if adjusted_f_star > 0.6:
        recommendation = f"综合建议：果断下重注。会商加权 f* = {adjusted_f_star:.2f}，多分身综合判断赔率足够高。"
    elif adjusted_f_star > 0.2:
        recommendation = f"综合建议：适度投入。会商加权 f* = {adjusted_f_star:.2f}，建议保留余量。"
    elif adjusted_f_star >= 0:
        recommendation = f"综合建议：观望或小注试探。会商加权 f* = {adjusted_f_star:.2f}，当前胜率或赔率不够理想。"
    else:
        recommendation = f"综合建议：主动撤出，保护核心资产。会商加权 f* = {adjusted_f_star:.2f}，不值得投入。"

    # ---- 冲突检测：分身意见分歧 ----
    f_stars = [r['f_star'] for r in persona_results]
    persona_conflict = False
    for i in range(len(f_stars)):
        for j in range(i + 1, len(f_stars)):
            if abs(f_stars[i] - f_stars[j]) > PERSONA_CONFLICT_THRESHOLD:
                persona_conflict = True
                break

    # ---- 各分身投票概览 ----
    votes = []
    for r in persona_results:
        votes.append(PersonaVote(
            persona_name=r['name'],
            f_star=round(r['f_star'], 4),
            weight=round(r['weight'], 4),
            summary=r.get('reasoning', '')[:100] + '...' if len(r.get('reasoning', '')) > 100 else r.get('reasoning', '')
        ))

    # ---- 冲突与降级提示 ----
    if survival_conflict:
        recommendation += "\n\n⚠️ " + survival_note
    if persona_conflict:
        recommendation += "\n\n⚠️ 分身意见分歧：不同分身的建议存在显著差异，请仔细审阅各分身独立意见后再做决定。"
    # P0 补强：风险 Agent 的生存/过载提示原先只存在于单分身链路，
    # 多分身主链路完全丢弃，导致 overload_signal 静默失效。
    advisory = risk_advisory(risk_result, survival_conflict)
    if advisory:
        recommendation += "\n\n" + advisory
    note = degraded_note(risk_result)
    if note:
        recommendation += "\n\n" + note

    risk_opinion = (
        f"风险等级：{risk_result.risk_level}"
        f"{'（已降级：AI 评估解析失败）' if risk_result.degraded else '（基于中性分身评估）'}\n"
        f"清零风险：{'是' if risk_result.bankruptcy_risk else '否'}\n"
        f"{risk_result.suggestion}"
    )

    return DecisionReport(
        loop_type="slow",
        recommendation=recommendation,
        f_star=round(adjusted_f_star, 4),
        risk_level="高" if survival_conflict else risk_result.risk_level,
        scenario_type=scenario_type,
        quant_opinion="多分身会商结果，详见各分身独立意见。",
        risk_opinion=risk_opinion,
        calculation_detail="多分身加权融合：各分身独立估算 p、b、f*，按权重加权平均。",
        scene_result=scene_result,
        persona_results=persona_results,  # 新增字段
        conflict_detected=persona_conflict or survival_conflict,
        risk_degraded=risk_result.degraded
    )
