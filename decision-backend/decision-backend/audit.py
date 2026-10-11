#audit.py
"""
L3 系统自校正：历史决策汇总审计

架构依据
--------
架构文档 6.4 节：L3 是最高层级的反馈回路，由用户主动或定期触发。元认知调度器
展示系统运行以来的汇总数据——各 Agent 的建议准确率、最常见的冲突类型、
Mux 仲裁的倾向性（保守/激进）——用户据此判断系统是否出现系统性偏差，
再亲手调整底层参数。

设计取舍（重要）
----------------
1. **不新增数据库列**。冲突标记、风险降级、场景识别、各分身结果等字段只存在于
   落库的报告 JSON（messages.content）里。本模块直接联结解析该 JSON，
   避免为一个统计功能引入 schema 迁移（当前 DB 没有迁移机制）。
2. **如实标注能力边界**。架构要求「各 Agent 的建议准确率」，但现有数据只有
   **决策级**反馈（useful / inaccurate），没有 Agent 级或分身级反馈
   （Phase 4.2.3 设计过分身级反馈，但表与接口都未实现）。因此本模块给出的是
   决策级准确率，并按场景类型分组作为「哪个 Agent 主导」的代理指标，
   同时在 limitations 中显式说明这一限制，绝不编造 Agent 级数字。
3. **容忍异构历史数据**。字段是分阶段加进来的（历史记录没有
   conflict_detected / risk_degraded，26 条没有 persona_results，
   26 条 scenario_type 为空），且存在消息被删除导致报告缺失的记录。
   所有读取一律用 .get() 并跳过缺失项。
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, Optional

from agent_core.mux import (
    ADVICE_BANDS,
    HEAVY_BET_THRESHOLD,
    SURVIVAL_CLAMP_FACTOR,
    advice_band,
)
from storage import get_decision_records_with_report

# f* 分档沿用 mux 的统一阈值（报告文案与审计分布必须同一口径）
# 注意：此处原先用 HEAVY_BET_THRESHOLD(0.5) 判「重注」，而报告文案在 0.6 才叫重注，
# 会出现「报告说适度投入、看板却统计成重注」的分裂，现统一走 advice_band。
MODERATE_BET = 0.2
# 触发强制降仓的阈值（统计生存约束用）
HEAVY_BET = HEAVY_BET_THRESHOLD
# 「接近生存降仓」的判定容差
CLAMP_TOLERANCE = 0.02
# 判定 f* 与凯利原始值「显著偏离」的阈值
DEVIATION_THRESHOLD = 0.05


# ==========================================
# 单条记录的解析与分类
# ==========================================

def _parse_report(raw: Any) -> Optional[dict]:
    """解析落库的报告 JSON；失败返回 None（历史数据可能损坏或被截断）。"""
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    return obj if isinstance(obj, dict) else None


def classify_f_star(f_star: Optional[float]) -> str:
    """把 f* 归入建议档位（与报告文案共用 mux.advice_band，避免口径分裂）。"""
    if f_star is None:
        return "未知"
    return advice_band(f_star)


def expected_pre_arbitration_f_star(record: dict, report: Optional[dict]) -> Optional[float]:
    """
    推算「仲裁前」的 f*，用于识别 Mux 的生存优先降仓。

    - 多分身报告：按各分身权重加权还原（分身结果里带 f_star 与 weight）
    - 单分身报告：凯利原始值 f* = p - q/b
    无法推算时返回 None。
    """
    if report:
        personas = report.get("persona_results")
        if isinstance(personas, list) and personas:
            total_weight = 0.0
            weighted = 0.0
            for persona in personas:
                if not isinstance(persona, dict):
                    continue
                try:
                    weight = float(persona.get("weight") or 0.0)
                    value = float(persona.get("f_star") or 0.0)
                except (TypeError, ValueError):
                    continue
                total_weight += weight
                weighted += value * weight
            if total_weight > 0:
                return weighted / total_weight

    p, q, b = record.get("p"), record.get("q"), record.get("b")
    try:
        p, q, b = float(p), float(q), float(b)
    except (TypeError, ValueError):
        return None
    if b == 0:
        return None
    return p - q / b


def looks_survival_clamped(expected: Optional[float], recorded: Optional[float]) -> bool:
    """
    识别生存优先硬约束是否生效：仲裁前 f* > 0.5 且记录值恰为原值 × 降仓系数。
    """
    if expected is None or recorded is None:
        return False
    if expected <= HEAVY_BET:
        return False
    return abs(recorded - expected * SURVIVAL_CLAMP_FACTOR) <= CLAMP_TOLERANCE


# ==========================================
# 汇总
# ==========================================

def _ratio(numerator: int, denominator: int) -> Optional[float]:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _scenario_type_variants(records: list) -> list:
    """
    检出「同一场景被写成多个标签」的数据质量问题。

    实测历史数据里同时存在「优势积累与动态反馈」与「优势积累与动态反馈场景」，
    说明场景类型由大模型自由生成、没有归一化，会让按场景分组的统计被稀释。
    """
    groups: dict = {}
    for record in records:
        label = (record.get("scenario_type") or "").strip()
        if not label:
            continue
        normalized = re.sub(r"场景$", "", label).strip()
        groups.setdefault(normalized, set()).add(label)
    return [
        {"normalized": key, "variants": sorted(variants), "count": len(variants)}
        for key, variants in sorted(groups.items())
        if len(variants) > 1
    ]


def month_key(created_at: Any) -> Optional[str]:
    """从 ISO 时间字符串取「YYYY-MM」；无法解析时返回 None。"""
    if not isinstance(created_at, str) or len(created_at) < 7:
        return None
    candidate = created_at[:7]
    return candidate if re.fullmatch(r"\d{4}-\d{2}", candidate) else None


def _accuracy(useful: int, inaccurate: int) -> Optional[float]:
    """决策级准确率：反馈为「有用」占已反馈的比例。无样本时返回 None，而不是 0。"""
    return _ratio(useful, useful + inaccurate)


def _empty_bucket(key: str) -> dict:
    return {"key": key, "decisions": 0, "with_feedback": 0, "useful": 0,
            "inaccurate": 0, "accuracy": None, "avg_f_star": None,
            "_f_sum": 0.0, "_f_count": 0}


def _finalize_bucket(bucket: dict) -> dict:
    decisions = bucket["decisions"]
    bucket["accuracy"] = _accuracy(bucket["useful"], bucket["inaccurate"])
    # 平均 f* 只按「有量化参数」的记录算，否则快回路会用占位 0 拉低均值
    bucket["avg_f_star"] = (round(bucket["_f_sum"] / bucket["_f_count"], 4)
                            if bucket["_f_count"] else None)
    bucket["feedback_coverage"] = _ratio(bucket["with_feedback"], decisions)
    bucket.pop("_f_sum", None)
    bucket.pop("_f_count", None)
    return bucket


def build_system_audit(records: Optional[list] = None) -> dict:
    """
    生成 L3 审计汇总。

    参数 records 可注入（便于测试）；缺省从数据库读取。
    """
    if records is None:
        records = get_decision_records_with_report()

    total = len(records)
    with_feedback = useful = inaccurate = 0
    reports_missing = reports_unparseable = 0
    fast_count = 0

    loop_dist: dict = {}
    risk_dist: dict = {}
    rec_mix: dict = {}
    by_scenario: dict = {}
    by_loop: dict = {}
    month_buckets: dict = {}

    scene_recognized = scene_total = 0
    conflict_count = degraded_count = persona_conflict_count = 0
    clamped_count = 0
    comparable = 0
    deviations = 0
    f_values = []

    for record in records:
        loop = record.get("loop_type") or "未知"
        loop_dist[loop] = loop_dist.get(loop, 0) + 1

        raw_report = record.get("report_json")
        if raw_report is None:
            reports_missing += 1
        report = _parse_report(raw_report)
        if raw_report is not None and report is None:
            reports_unparseable += 1

        feedback = record.get("feedback_type")
        if feedback == "useful":
            useful += 1
            with_feedback += 1
        elif feedback == "inaccurate":
            inaccurate += 1
            with_feedback += 1

        # 快回路决策也落库（loop_type="fast"），但没有量化参数：
        # p/q/b/f_star 只是满足 NOT NULL 的占位 0，绝不能进入任何按 f* 的统计。
        has_params = bool(record.get("params_available", 1))
        if not has_params:
            fast_count += 1

        f_star = record.get("f_star")
        try:
            f_star = float(f_star)
        except (TypeError, ValueError):
            f_star = None
        if has_params and f_star is not None:
            f_values.append(f_star)
        elif not has_params:
            f_star = None

        band = classify_f_star(f_star) if has_params else None
        if band:
            rec_mix[band] = rec_mix.get(band, 0) + 1

        # 按月聚合（供 L3 看板画趋势）
        mkey = month_key(record.get("created_at"))
        if mkey:
            mb = month_buckets.setdefault(mkey, {
                "key": mkey, "decisions": 0, "useful": 0, "inaccurate": 0,
                "with_feedback": 0, "heavy_bet": 0, "_f_sum": 0.0, "_f_count": 0,
            })
            mb["decisions"] += 1
            if feedback == "useful":
                mb["useful"] += 1
                mb["with_feedback"] += 1
            elif feedback == "inaccurate":
                mb["inaccurate"] += 1
                mb["with_feedback"] += 1
            if band == "重注":
                mb["heavy_bet"] += 1
            if has_params and f_star is not None:
                mb["_f_sum"] += f_star
                mb["_f_count"] += 1

        scenario_key = (record.get("scenario_type") or "").strip() or "（未识别）"
        bucket = by_scenario.setdefault(scenario_key, _empty_bucket(scenario_key))
        bucket["decisions"] += 1
        if feedback == "useful":
            bucket["useful"] += 1
            bucket["with_feedback"] += 1
        elif feedback == "inaccurate":
            bucket["inaccurate"] += 1
            bucket["with_feedback"] += 1
        if has_params and f_star is not None:
            bucket["_f_sum"] += f_star
            bucket["_f_count"] += 1

        loop_bucket = by_loop.setdefault(loop, _empty_bucket(loop))
        loop_bucket["decisions"] += 1
        if feedback == "useful":
            loop_bucket["useful"] += 1
            loop_bucket["with_feedback"] += 1
        elif feedback == "inaccurate":
            loop_bucket["inaccurate"] += 1
            loop_bucket["with_feedback"] += 1
        if has_params and f_star is not None:
            loop_bucket["_f_sum"] += f_star
            loop_bucket["_f_count"] += 1

        if report:
            level = report.get("risk_level")
            if level:
                risk_dist[str(level)] = risk_dist.get(str(level), 0) + 1

            scene = report.get("scene_result")
            if isinstance(scene, dict) and "scene_recognized" in scene:
                scene_total += 1
                if scene.get("scene_recognized"):
                    scene_recognized += 1

            if report.get("conflict_detected"):
                conflict_count += 1
            if report.get("risk_degraded"):
                degraded_count += 1
            personas = report.get("persona_results")
            if isinstance(personas, list) and len(personas) > 1:
                stars = [p.get("f_star") for p in personas if isinstance(p, dict)]
                stars = [float(s) for s in stars if isinstance(s, (int, float))]
                if stars and (max(stars) - min(stars)) > 0.4:
                    persona_conflict_count += 1

        expected = expected_pre_arbitration_f_star(record, report)
        if expected is not None and f_star is not None:
            comparable += 1
            if abs(f_star - expected) > DEVIATION_THRESHOLD:
                deviations += 1
            if looks_survival_clamped(expected, f_star):
                clamped_count += 1

    scenario_rows = sorted(
        (_finalize_bucket(b) for b in by_scenario.values()),
        key=lambda row: (-row["decisions"], row["key"]),
    )
    loop_rows = sorted(
        (_finalize_bucket(b) for b in by_loop.values()),
        key=lambda row: (-row["decisions"], row["key"]),
    )

    # 月度趋势（按时间正序，供看板画折线/柱状）
    trend_rows = []
    for key in sorted(month_buckets):
        mb = month_buckets[key]
        decisions = mb["decisions"]
        trend_rows.append({
            "month": key,
            "decisions": decisions,
            "with_feedback": mb["with_feedback"],
            "feedback_coverage": _ratio(mb["with_feedback"], decisions),
            "accuracy": _accuracy(mb["useful"], mb["inaccurate"]),
            "heavy_bet_count": mb["heavy_bet"],
            "heavy_bet_share": (_ratio(mb["heavy_bet"], mb["_f_count"])
                                if mb["_f_count"] else None),
            "avg_f_star": (round(mb["_f_sum"] / mb["_f_count"], 4)
                           if mb["_f_count"] else None),
        })

    created = [r.get("created_at") for r in records if r.get("created_at")]

    return {
        "generated_at": datetime.now().isoformat(),
        "window": {"start": min(created) if created else None,
                   "end": max(created) if created else None},
        "totals": {
            "decisions": total,
            "with_feedback": with_feedback,
            "useful": useful,
            "inaccurate": inaccurate,
            "feedback_coverage": _ratio(with_feedback, total),
            "reports_missing": reports_missing,
            "reports_unparseable": reports_unparseable,
            # P2：快回路决策现已落库，但参数无意义，单独计数
            "fast_decisions": fast_count,
            "with_quant_params": total - fast_count,
        },
        # 决策级准确率（非 Agent 级，见 limitations）
        "decision_accuracy": {
            "value": _accuracy(useful, inaccurate),
            "sample": useful + inaccurate,
        },
        "loop_distribution": loop_dist,
        "recommendation_mix": rec_mix,
        "recommendation_mix_ratio": {
            band: _ratio(count, total - fast_count if total - fast_count > 0 else total)
            for band, count in sorted(rec_mix.items())
        },
        "risk_level_distribution": risk_dist,
        "avg_f_star": round(sum(f_values) / len(f_values), 4) if f_values else None,
        "negative_f_star_share": _ratio(sum(1 for v in f_values if v < 0), len(f_values)),
        "by_scenario_type": scenario_rows,
        "by_loop_type": loop_rows,
        "trend_by_month": trend_rows,
        "quality": {
            "reports_usable": total - reports_missing - reports_unparseable,
            "scene_recognized_rate": _ratio(scene_recognized, scene_total),
            "conflict_rate": _ratio(conflict_count, total),
            "persona_conflict_count": persona_conflict_count,
            "risk_degraded_rate": _ratio(degraded_count, total),
            # Mux 仲裁倾向：被生存优先硬约束下调的决策占比
            "survival_clamped_count": clamped_count,
            "survival_clamp_rate": _ratio(clamped_count, comparable),
            "f_star_vs_pre_arbitration_deviations": deviations,
            "f_star_comparable": comparable,
        },
        "mux_parameters": {
            "heavy_bet_threshold": HEAVY_BET,
            "survival_clamp_factor": SURVIVAL_CLAMP_FACTOR,
            "persona_conflict_threshold": 0.4,
        },
        "data_quality": {
            "scenario_type_variants": _scenario_type_variants(records),
        },
        # P1-4：关系边界条件属于架构 6.4 所说的「用户亲手调整的底层参数」，
        # 随审计一并展示，让用户能看到当前伦理边界的触发条件。
        "boundary_config": _safe_boundary_config(),
        "capability_profile": _safe_profile(),
        "limitations": [
            "准确率为**决策级**，来自用户对整份报告的 useful/inaccurate 反馈，"
            "不是各 Agent 的独立准确率。现有数据不支持按 Agent 拆分。",
            "Phase 4.2.3 设计过分身级反馈（decision_records.persona_feedback），"
            "但表与接口均未实现，因此无法衡量单个分身的建议质量。",
            "快回路决策已落库并计入回路分布与准确率，但它没有量化参数"
            "（params_available=0），因此不参与任何按 f* 的统计；"
            "改动之前的历史快回路决策没有记录，fast 计数只反映此后产生的数据。",
            "survival_clamp_rate 只识别「仲裁前 f* > 0.5 且记录值 = 原值 × "
            f"{SURVIVAL_CLAMP_FACTOR}」这一精确形态；早期记录不含仲裁，历史值恒为未被下调。",
            "历史记录字段不齐（26 条无 persona_results、26 条 scenario_type 为空），"
            "相关比例的分母已按实际可用数据计算。",
        ],
    }


def _safe_profile() -> dict:
    """读取当前能力画像；向量库不可用时降级为空（不阻断审计）。"""
    try:
        from vector_store import get_user_profile
        profile = get_user_profile() or {}
        return {k: v for k, v in profile.items() if not k.endswith("_basis")}
    except Exception as e:  # noqa: BLE001
        logging.warning("[L3审计] 读取能力画像失败，已跳过：%s", e)
        return {}


def _safe_boundary_config() -> dict:
    """读取关系边界配置；失败时返回空字典，不阻断审计。"""
    try:
        from boundary_config import config_metadata
        return config_metadata()
    except Exception as e:  # noqa: BLE001
        logging.warning("[L3审计] 读取关系边界配置失败，已跳过：%s", e)
        return {}
