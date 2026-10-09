# -*- coding: utf-8 -*-
"""Mux 仲裁测试（P0-3：生存优先硬约束必须在单分身与多分身两条链路上都生效）"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import support  # noqa: F401

from agent_core.mux import (  # noqa: E402
    SURVIVAL_CLAMP_FACTOR, apply_survival_constraint, merge,
)
from agent_core.persona_mux import merge_personas  # noqa: E402
from models.schemas import QuantResult, RiskResult  # noqa: E402


def risk(level="低", bankruptcy=False, degraded=False, suggestion="风险说明"):
    return RiskResult(risk_level=level, bankruptcy_risk=bankruptcy,
                      overload_signal=False, zoh_recommend=False,
                      suggestion=suggestion, degraded=degraded)


def quant(f_star=0.89, scenario_type="高赔率重注场景"):
    return QuantResult(p=0.9, q=0.1, b=10.0, f_star=f_star,
                       scenario_type=scenario_type, reasoning="推理")


def persona_results(f_stars, weights=None):
    weights = weights or [1 / len(f_stars)] * len(f_stars)
    out = []
    for i, (f, w) in enumerate(zip(f_stars, weights)):
        out.append({
            "persona_id": i + 1, "name": f"分身{i + 1}", "risk_preference": "neutral",
            "weight": w, "p": 0.8, "q": 0.2, "b": 5.0, "f_star": f,
            "scenario_type": "高赔率重注场景", "reasoning": "分析意见",
        })
    return out


class TestApplySurvivalConstraint(unittest.TestCase):
    def test_heavy_bet_plus_bankruptcy_is_clamped(self):
        adjusted, conflict, note = apply_survival_constraint(0.9, risk(bankruptcy=True, level="高"))
        self.assertTrue(conflict)
        self.assertAlmostEqual(adjusted, 0.9 * SURVIVAL_CLAMP_FACTOR, places=4)
        self.assertIn("生存优先硬约束", note)

    def test_moderate_bet_is_untouched(self):
        adjusted, conflict, _ = apply_survival_constraint(0.3, risk(bankruptcy=True, level="高"))
        self.assertFalse(conflict)
        self.assertAlmostEqual(adjusted, 0.3, places=4)

    def test_no_bankruptcy_is_untouched(self):
        adjusted, conflict, _ = apply_survival_constraint(0.9, risk(bankruptcy=False))
        self.assertFalse(conflict)
        self.assertAlmostEqual(adjusted, 0.9, places=4)

    def test_floor_is_respected(self):
        adjusted, _, _ = apply_survival_constraint(0.6, risk(bankruptcy=True, level="高"))
        self.assertGreaterEqual(adjusted, -0.3)


class TestSinglePersonaMerge(unittest.TestCase):
    def test_bankruptcy_overrides_heavy_bet(self):
        report = merge(quant(0.89), risk(bankruptcy=True, level="高"))
        self.assertAlmostEqual(report.f_star, 0.89 * SURVIVAL_CLAMP_FACTOR, places=4)
        self.assertEqual(report.risk_level, "高")
        self.assertTrue(report.conflict_detected)
        self.assertIn("冲突检测", report.recommendation)

    def test_scenario_type_is_preserved(self):
        report = merge(quant(0.5, "低赔率做空场景"), risk(level="中"))
        self.assertEqual(report.scenario_type, "低赔率做空场景")

    def test_degraded_risk_is_surfaced(self):
        report = merge(quant(0.3), risk(level="高", bankruptcy=True, degraded=True, suggestion="降级说明"))
        self.assertIn("降级", report.recommendation)
        self.assertIn("降级说明", report.risk_opinion)


class TestMultiPersonaMerge(unittest.TestCase):
    """P0 核心回归：多分身链路原先丢掉 bankruptcy_risk，硬约束形同虚设。"""

    def test_bankruptcy_now_clamps_weighted_f_star(self):
        results = persona_results([0.9, 0.9, 0.9])
        report = merge_personas(
            persona_results=results, weighted_f_star=0.9,
            risk_result=risk(level="高", bankruptcy=True, suggestion="不要满仓"),
            scenario_type="高赔率重注场景",
        )
        self.assertAlmostEqual(report.f_star, 0.9 * SURVIVAL_CLAMP_FACTOR, places=4)
        self.assertEqual(report.risk_level, "高")
        self.assertTrue(report.conflict_detected)
        self.assertIn("生存优先硬约束", report.recommendation)

    def test_risk_suggestion_is_no_longer_discarded(self):
        report = merge_personas(
            persona_results=persona_results([0.5]), weighted_f_star=0.5,
            risk_result=risk(level="中", bankruptcy=False, suggestion="建议保留余量"),
            scenario_type="通用",
        )
        self.assertIn("建议保留余量", report.risk_opinion)
        self.assertIn("清零风险：否", report.risk_opinion)

    def test_scenario_type_is_propagated(self):
        report = merge_personas(
            persona_results=persona_results([0.5]), weighted_f_star=0.5,
            risk_result=risk(), scenario_type="优势积累与动态反馈场景",
        )
        self.assertEqual(report.scenario_type, "优势积累与动态反馈场景")

    def test_persona_disagreement_sets_conflict_flag(self):
        report = merge_personas(
            persona_results=persona_results([0.9, 0.2]),
            weighted_f_star=0.55, risk_result=risk(), scenario_type="通用",
        )
        self.assertTrue(report.conflict_detected)
        self.assertIn("分身意见分歧", report.recommendation)

    def test_no_conflict_when_personas_agree(self):
        report = merge_personas(
            persona_results=persona_results([0.5, 0.55]),
            weighted_f_star=0.52, risk_result=risk(), scenario_type="通用",
        )
        self.assertFalse(report.conflict_detected)

    def test_degraded_risk_is_surfaced(self):
        report = merge_personas(
            persona_results=persona_results([0.4]), weighted_f_star=0.4,
            risk_result=risk(level="高", bankruptcy=True, degraded=True),
            scenario_type="通用",
        )
        self.assertIn("降级", report.recommendation)
        self.assertIn("已降级", report.risk_opinion)

    def test_persona_results_are_returned_to_caller(self):
        results = persona_results([0.5, 0.6])
        report = merge_personas(
            persona_results=results, weighted_f_star=0.55,
            risk_result=risk(), scenario_type="通用",
        )
        self.assertEqual(len(report.persona_results), 2)
        self.assertEqual(report.persona_results[0]["name"], "分身1")


class TestSharedImplementation(unittest.TestCase):
    """两条链路必须共用同一份仲裁逻辑，避免再次漂移。"""

    def test_both_paths_agree_on_clamping(self):
        single = merge(quant(0.8), risk(bankruptcy=True, level="高")).f_star
        multi = merge_personas(
            persona_results=persona_results([0.8]), weighted_f_star=0.8,
            risk_result=risk(bankruptcy=True, level="高"), scenario_type="通用",
        ).f_star
        self.assertAlmostEqual(single, multi, places=6)


if __name__ == "__main__":
    unittest.main()
