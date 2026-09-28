#agent_core/mux.py
"""
Mux 多路复用/融合器
职责：仲裁和融合多个Agent的输出，生成统一的决策建议。

Phase 1 实现方式：
- 简单加权融合（量化0.6，风险0.4）
- 优先级仲裁：破产风险警报 > 量化建议
- 后续可升级为卡尔曼滤波或贝叶斯融合
"""

from models.schemas import QuantResult, RiskResult, DecisionReport


def merge(quant_result: QuantResult, risk_result: RiskResult,scene_result=None) -> DecisionReport:
    """
    融合量化分析和风险评估的结果，生成最终决策建议。
    
    参数:
        quant_result: 量化分析Agent的输出
        risk_result: 风险监控Agent的输出
    
    返回:
        DecisionReport: 综合决策建议
    Phase 2 新增：融合场景策略结果。
    """
    
    # ========================================
    # 第一阶段：冲突检测与优先级仲裁
    # ========================================
    
    # 优先级规则：破产风险 > 量化建议
    conflict_detected = False
    conflict_note = ""
    
    if risk_result.bankruptcy_risk and quant_result.f_star > 0.5:
        conflict_detected = True
        conflict_note = (
            f"冲突检测：量化Agent建议重注(f*={quant_result.f_star:.2f})，"
            f"但风险Agent检测到清零风险。按照生存优先硬约束，以风险建议为准。"
        )
    elif quant_result.f_star < 0 and risk_result.risk_level == "低":
        conflict_detected = True
        conflict_note = (
            f"注意：量化Agent建议做空(f*={quant_result.f_star:.2f})，"
            f"但风险Agent未检测到显著风险。请结合自身实际情况判断。"
        )
    
    # ========================================
    # 第二阶段：融合建议生成
    # ========================================
    
    # 确定最终风险等级
    if conflict_detected and risk_result.bankruptcy_risk:
        final_risk_level = "高"
        adjusted_f_star = max(-0.3, quant_result.f_star * 0.3)  # 强制降低
    else:
        final_risk_level = risk_result.risk_level
        adjusted_f_star = quant_result.f_star
    
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
    
    # 构建 DecisionReport
    return DecisionReport(
        recommendation="\n".join(recommendation_parts),
        f_star=round(adjusted_f_star, 4),
        risk_level=final_risk_level,
        scenario_type=quant_result.scenario_type,
        quant_opinion=f"胜率p={quant_result.p:.2f}, 败率q={quant_result.q:.2f}, 赔率b={quant_result.b:.1f}\n{quant_result.reasoning}",
        risk_opinion=f"风险等级：{risk_result.risk_level}\n清零风险：{'是' if risk_result.bankruptcy_risk else '否'}\n{risk_result.suggestion}",
        calculation_detail=quant_result.reasoning,
        scene_result=scene_result  # Phase 2 新增
    )