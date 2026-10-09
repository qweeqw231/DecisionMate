#agent_core/mux.py
"""
Mux 多路复用/融合器
职责：仲裁和融合多个Agent的输出，生成统一的决策建议。

Phase 1 实现方式：
- 优先级仲裁：破产风险警报 > 量化建议
- 后续可升级为卡尔曼滤波或贝叶斯融合

P0 修复说明
-----------
原先「破产风险 → 强制降仓」的仲裁逻辑只写在单分身 merge() 里，而系统运行时
只要存在分身就一定走多分身 merge_personas()（persona_mux.py），且后者只接收
risk_level、丢掉了 bankruptcy_risk——于是架构「原则四：生存优先硬约束」在
**主链路上从未生效**。

现在把该仲裁抽成 apply_survival_constraint()，由 merge() 与 merge_personas()
共用同一份实现，消除两条链路行为漂移的可能。
"""

from models.schemas import QuantResult, RiskResult, DecisionReport

# 触发强制降仓的「重注」阈值：f* 高于此值且风险 Agent 报清零风险时，视为实质性冲突
HEAVY_BET_THRESHOLD = 0.5
# 冲突时的降仓系数与下限（沿用 Phase 1 的量级：f* × 0.3，且不低于 -0.3）
SURVIVAL_CLAMP_FACTOR = 0.3
SURVIVAL_CLAMP_FLOOR = -0.3


def apply_survival_constraint(f_star: float, risk_result: RiskResult) -> tuple[float, bool, str]:
    """
    生存优先硬约束：当「量化/会商建议重注」与「风险 Agent 报清零风险」冲突时，
    按架构 4.2 原则四强制输出保守建议。

    返回:
        (调整后的 f*, 是否触发冲突, 冲突说明文本)
    """
    if risk_result.bankruptcy_risk and f_star > HEAVY_BET_THRESHOLD:
        adjusted = max(SURVIVAL_CLAMP_FLOOR, f_star * SURVIVAL_CLAMP_FACTOR)
        note = (
            f"冲突检测：建议重注(f*={f_star:.2f})，但风险Agent检测到清零风险。"
            f"按生存优先硬约束下调至 f*={adjusted:.2f}（原值 × {SURVIVAL_CLAMP_FACTOR}）。"
        )
        return adjusted, True, note
    return f_star, False, ""


def degraded_note(risk_result: RiskResult) -> str:
    """风险 Agent 降级（解析失败）时的显式提示，避免把降级结果误当成真实评估。"""
    if not risk_result.degraded:
        return ""
    return (
        "⚠️ 风险Agent本次未能返回可解析的评估，系统已按「生存优先」降级为保守处理；"
        "该结论未经完整风险校验，请人工复核。"
    )


def merge(quant_result: QuantResult, risk_result: RiskResult, scene_result=None) -> DecisionReport:
    """
    融合量化分析和风险评估的结果，生成最终决策建议。

    参数:
        quant_result: 量化分析Agent的输出
        risk_result:  风险监控Agent的输出
        scene_result: 场景策略Agent的输出（Phase 2 新增）

    返回:
        DecisionReport: 综合决策建议
    """

    # ========================================
    # 第一阶段：冲突检测与优先级仲裁
    # ========================================

    adjusted_f_star, survival_conflict, conflict_note = apply_survival_constraint(
        quant_result.f_star, risk_result
    )
    conflict_detected = survival_conflict

    # 次级规则：量化建议做空，但风险 Agent 未识别到显著风险
    if not conflict_detected and quant_result.f_star < 0 and risk_result.risk_level == "低":
        conflict_detected = True
        conflict_note = (
            f"注意：量化Agent建议做空(f*={quant_result.f_star:.2f})，"
            f"但风险Agent未检测到显著风险。请结合自身实际情况判断。"
        )

    # ========================================
    # 第二阶段：融合建议生成
    # ========================================

    final_risk_level = "高" if survival_conflict else risk_result.risk_level

    # 生成综合建议文本
    recommendation_parts = []

    # 核心建议
    if adjusted_f_star > 0.6:
        recommendation_parts.append("综合建议：果断下重注。")
        recommendation_parts.append(f"当前决策属于{quant_result.scenario_type}，赔率足够高，应全力投入约{adjusted_f_star:.0%}的可用资源。")
    elif adjusted_f_star > 0.2:
        recommendation_parts.append("综合建议：适度投入。")
        recommendation_parts.append(f"可投入约{adjusted_f_star:.0%}的精力/资源，保留余量应对不确定性。")
    elif adjusted_f_star >= 0:
        recommendation_parts.append("综合建议：观望或小注试探。")
        recommendation_parts.append(f"当前胜率或赔率不够理想(f*={adjusted_f_star:.2f})，建议小注获取更多信息后再做判断。")
    else:
        recommendation_parts.append("综合建议：主动撤出，保护核心资产。")
        recommendation_parts.append(f"凯利公式计算结果为负(f*={adjusted_f_star:.2f})，此决策不值得投入。将精力留给更值得的战场。")

    # 融合风险建议
    if final_risk_level == "高":
        recommendation_parts.append("风险警告：存在清零风险，生存优先硬约束已激活。请勿突破自身底线。")
    elif risk_result.overload_signal:
        recommendation_parts.append("健康提醒：检测到过载信号。参照5月13号案例，一次主动休整胜过十次被动崩溃。")

    if conflict_detected:
        recommendation_parts.append(conflict_note)

    note = degraded_note(risk_result)
    if note:
        recommendation_parts.append(note)

    # 构建 DecisionReport
    return DecisionReport(
        recommendation="\n".join(recommendation_parts),
        f_star=round(adjusted_f_star, 4),
        risk_level=final_risk_level,
        scenario_type=quant_result.scenario_type,
        quant_opinion=f"胜率p={quant_result.p:.2f}, 败率q={quant_result.q:.2f}, 赔率b={quant_result.b:.1f}\n{quant_result.reasoning}",
        risk_opinion=f"风险等级：{risk_result.risk_level}\n清零风险：{'是' if risk_result.bankruptcy_risk else '否'}\n{risk_result.suggestion}",
        calculation_detail=quant_result.reasoning,
        scene_result=scene_result,  # Phase 2 新增
        # P0 修复：原先未回填该字段，单分身链路即使触发了硬约束也不会亮冲突标记
        conflict_detected=conflict_detected
    )
