#agent_core/persona_mux.py
"""
多分身融合器（Persona Mux）
职责：加权融合多个分身的独立分析结果，生成会商摘要。
"""

from typing import List
from models.schemas import QuantResult, DecisionReport, PersonaVote


def merge_personas(persona_results: List[dict], weighted_f_star: float,
                   risk_level: str, scenario_type: str, scene_result=None) -> DecisionReport:
    """
    融合多分身分析结果。

    参数:
        persona_results: 各分身的分析结果列表，每项包含 name, p, q, b, f_star, reasoning, weight
        weighted_f_star: 加权后的 f*
        risk_level: 风险等级（来自中性分身的风险评估）
        scenario_type: 场景类型
        scene_result: 场景策略结果

    返回:
        DecisionReport: 会商摘要 + 各分身投票概览 + 综合建议
    """
    # 综合建议生成
    if weighted_f_star > 0.6:
        recommendation = f"综合建议：果断下重注。会商加权 f* = {weighted_f_star:.2f}，多分身综合判断赔率足够高。"
    elif weighted_f_star > 0.2:
        recommendation = f"综合建议：适度投入。会商加权 f* = {weighted_f_star:.2f}，建议保留余量。"
    elif weighted_f_star >= 0:
        recommendation = f"综合建议：观望或小注试探。会商加权 f* = {weighted_f_star:.2f}，当前胜率或赔率不够理想。"
    else:
        recommendation = f"综合建议：主动撤出，保护核心资产。会商加权 f* = {weighted_f_star:.2f}，不值得投入。"

    # 冲突检测：任意两个分身的 f* 差异超过 0.4
    f_stars = [r['f_star'] for r in persona_results]
    conflict = False
    for i in range(len(f_stars)):
        for j in range(i + 1, len(f_stars)):
            if abs(f_stars[i] - f_stars[j]) > 0.4:
                conflict = True
                break

    # 各分身投票概览
    votes = []
    for r in persona_results:
        votes.append(PersonaVote(
            persona_name=r['name'],
            f_star=round(r['f_star'], 4),
            weight=round(r['weight'], 4),
            summary=r.get('reasoning', '')[:100] + '...' if len(r.get('reasoning', '')) > 100 else r.get('reasoning', '')
        ))

    # 综合建议文本拼接
    if conflict:
        recommendation += "\n\n⚠️ 分身意见分歧：不同分身的建议存在显著差异，请仔细审阅各分身独立意见后再做决定。"

    return DecisionReport(
        loop_type="slow",
        recommendation=recommendation,
        f_star=round(weighted_f_star, 4),
        risk_level=risk_level,
        scenario_type=scenario_type,
        quant_opinion="多分身会商结果，详见各分身独立意见。",
        risk_opinion=f"风险等级：{risk_level}（基于中性分身评估）",
        calculation_detail="多分身加权融合：各分身独立估算 p、b、f*，按权重加权平均。",
        scene_result=scene_result,
        persona_results=persona_results,  # 新增字段
        conflict_detected=conflict
    )