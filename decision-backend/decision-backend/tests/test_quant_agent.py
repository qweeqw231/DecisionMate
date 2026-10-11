# -*- coding: utf-8 -*-
"""量化 Agent 的确定性 f* 与参数校验测试（P2-1）"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import support  # noqa: F401

from agent_core import quant_agent  # noqa: E402
from kelly import kelly_fraction  # noqa: E402


def analyze_with(payload):
    original = quant_agent.chat
    quant_agent.chat = lambda **kwargs: payload
    try:
        return quant_agent.analyze("测试场景")
    finally:
        quant_agent.chat = original


def payload(**overrides):
    base = {"p": 0.85, "q": 0.15, "b": 8.0, "f_star": 0.83,
            "scenario_type": "高赔率重注场景", "reasoning": "推理"}
    base.update(overrides)
    return json.dumps(base, ensure_ascii=False)


class TestDeterministicFStar(unittest.TestCase):
    """P2：f* 一律由凯利引擎复算，不再采信模型给的数字。"""

    def test_f_star_is_recomputed(self):
        result = analyze_with(payload(p=0.9, q=0.1, b=10.0, f_star=0.11))
        self.assertAlmostEqual(result.f_star, round(kelly_fraction(0.9, 10.0), 4), places=6)

    def test_hallucinated_f_star_cannot_exceed_one(self):
        """
        回归：模型曾可以返回 f*=4.7，前端会渲染成「全力投入 470% 的可用资源」。
        """
        result = analyze_with(payload(p=0.9, q=0.1, b=10.0, f_star=4.7))
        self.assertLessEqual(result.f_star, 1.0)
        self.assertAlmostEqual(result.f_star, 0.89, places=4)
        self.assertIn("[系统校正]", result.reasoning)
        self.assertIn("偏差较大", result.reasoning)

    def test_close_model_value_is_not_flagged(self):
        exact = round(kelly_fraction(0.85, 8.0), 4)
        result = analyze_with(payload(f_star=exact))
        self.assertNotIn("[系统校正]", result.reasoning)

    def test_missing_model_f_star_is_tolerated(self):
        raw = json.dumps({"p": 0.85, "q": 0.15, "b": 8.0,
                          "scenario_type": "x", "reasoning": "r"}, ensure_ascii=False)
        result = analyze_with(raw)
        self.assertAlmostEqual(result.f_star, round(kelly_fraction(0.85, 8.0), 4), places=6)

    def test_non_numeric_model_f_star_is_tolerated(self):
        result = analyze_with(payload(f_star="很高"))
        self.assertAlmostEqual(result.f_star, round(kelly_fraction(0.85, 8.0), 4), places=6)


class TestConsistencyCorrections(unittest.TestCase):
    def test_q_is_forced_to_one_minus_p(self):
        result = analyze_with(payload(p=0.8, q=0.5, b=4.0))
        self.assertAlmostEqual(result.q, 0.2, places=4)
        self.assertIn("不一致", result.reasoning)

    def test_consistent_q_is_not_flagged(self):
        result = analyze_with(payload(p=0.8, q=0.2, b=4.0))
        self.assertAlmostEqual(result.q, 0.2, places=4)
        self.assertNotIn("[系统校正]", result.reasoning)

    def test_small_q_rounding_difference_is_tolerated(self):
        result = analyze_with(payload(p=0.85, q=0.14, b=8.0))
        self.assertNotIn("[系统校正]", result.reasoning)


class TestDomainValidation(unittest.TestCase):
    """参数越界不得产出看似合理的数字，直接回退到安全默认值。"""

    def _assert_defaults(self, result):
        self.assertEqual(result.p, 0.5)
        self.assertEqual(result.q, 0.5)
        self.assertEqual(result.b, 1.0)
        self.assertEqual(result.f_star, 0.0)  # = kelly(0.5, 1.0)，与默认参数自洽
        self.assertIn("解析异常", result.scenario_type)

    def test_probability_above_one(self):
        self._assert_defaults(analyze_with(payload(p=1.4)))

    def test_probability_below_zero(self):
        self._assert_defaults(analyze_with(payload(p=-0.2)))

    def test_non_positive_odds(self):
        self._assert_defaults(analyze_with(payload(b=0)))
        self._assert_defaults(analyze_with(payload(b=-3)))

    def test_none_values(self):
        self._assert_defaults(analyze_with(payload(p=None)))

    def test_missing_required_fields(self):
        raw = json.dumps({"scenario_type": "x"}, ensure_ascii=False)
        self._assert_defaults(analyze_with(raw))

    def test_unparseable_output(self):
        self._assert_defaults(analyze_with("抱歉，我无法分析。"))

    def test_defaults_are_internally_consistent(self):
        """默认参数也必须满足 f* = p - (1-p)/b，否则报告自相矛盾。"""
        result = analyze_with("不是 JSON")
        self.assertAlmostEqual(result.f_star, round(kelly_fraction(result.p, result.b), 4), places=6)


if __name__ == "__main__":
    unittest.main()
