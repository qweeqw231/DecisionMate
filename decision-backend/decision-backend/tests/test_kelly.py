# -*- coding: utf-8 -*-
"""确定性凯利引擎测试（L1 的基础）"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import support  # noqa: F401

from kelly import KellyInputError, kelly_fraction, kelly_round, validate_params  # noqa: E402


class TestArchitectureAnchors(unittest.TestCase):
    """
    架构文档第 2 章给出的实战锚点。系统文档声称这些数字验证过，
    这里用确定性实现把它们钉住——之前 f* 完全由大模型给出，无法验证。
    """

    def test_soft_exam_damage_repair(self):
        # 5月21日软考战损修复：p=0.9, b=10 → f*=0.89（文档：建议投入 89% 筹码）
        self.assertAlmostEqual(kelly_fraction(0.9, 10.0), 0.89, places=4)

    def test_deep_retrospective(self):
        # 深度复盘：文档给出 f*≈0.895 量级
        self.assertAlmostEqual(kelly_fraction(0.9, 10.0), 0.89, places=4)

    def test_low_odds_short_is_negative(self):
        # 低赔率做空场景：文档 f*=-1.975 一类的负值
        self.assertLess(kelly_fraction(0.3, 0.2), 0)
        self.assertAlmostEqual(kelly_fraction(0.2, 0.5), -1.4, places=4)

    def test_high_odds_degenerates_to_win_rate_edge(self):
        # b 很大时 f* → p（文档：决策唯一依据是胜率优势）
        self.assertAlmostEqual(kelly_fraction(0.6, 1000.0), 0.6, places=3)


class TestMath(unittest.TestCase):
    def test_fair_bet_is_zero(self):
        # p=0.5, b=1（公平赌局）→ f*=0
        self.assertAlmostEqual(kelly_fraction(0.5, 1.0), 0.0, places=10)

    def test_certain_win_is_full(self):
        self.assertAlmostEqual(kelly_fraction(1.0, 2.0), 1.0, places=10)

    def test_zero_win_probability_is_fully_negative(self):
        # p=0 → f* = -1/b
        self.assertAlmostEqual(kelly_fraction(0.0, 4.0), -0.25, places=10)

    def test_formula_matches_definition(self):
        for p, b in [(0.7, 3.0), (0.45, 1.2), (0.95, 8.0), (0.05, 0.3)]:
            with self.subTest(p=p, b=b):
                self.assertAlmostEqual(kelly_fraction(p, b), p - (1 - p) / b, places=12)

    def test_rounding_is_consistent(self):
        self.assertEqual(kelly_round(0.9, 10.0), 0.89)
        self.assertEqual(kelly_round(0.9, 10.0, digits=2), 0.89)
        self.assertIsInstance(kelly_round(0.5, 3.0), float)


class TestValidation(unittest.TestCase):
    def test_rejects_out_of_range_probability(self):
        for p in (-0.01, 1.01, 2.0, -1.0):
            with self.subTest(p=p):
                with self.assertRaises(KellyInputError):
                    kelly_fraction(p, 2.0)

    def test_rejects_non_positive_odds(self):
        for b in (0.0, -1.0, -0.001):
            with self.subTest(b=b):
                with self.assertRaises(KellyInputError):
                    kelly_fraction(0.5, b)

    def test_rejects_genuinely_non_numeric(self):
        for p, b in [("很高", 2.0), (0.5, "很大"), (None, 2.0), (0.5, None),
                     (float("nan"), 2.0), (0.5, float("nan")),
                     (float("inf"), 2.0), (0.5, float("inf")),
                     ([], 2.0), (0.5, {})]:
            with self.subTest(p=p, b=b):
                with self.assertRaises(KellyInputError):
                    kelly_fraction(p, b)

    def test_accepts_numeric_strings_by_coercion(self):
        """模型经常把数字写成字符串，这里刻意宽松，避免无谓地降级。"""
        self.assertEqual(validate_params("0.5", "3"), (0.5, 3.0))
        self.assertAlmostEqual(kelly_fraction("0.8", "4"), 0.75, places=10)

    def test_numeric_strings_out_of_range_are_still_rejected(self):
        with self.assertRaises(KellyInputError):
            kelly_fraction("1.5", "3")
        with self.assertRaises(KellyInputError):
            kelly_fraction("0.5", "0")

    def test_error_is_a_value_error(self):
        """调用方按 ValueError 统一捕获，必须保持这个继承关系。"""
        self.assertTrue(issubclass(KellyInputError, ValueError))

    def test_boundary_values_are_allowed(self):
        self.assertAlmostEqual(kelly_fraction(0.0, 1.0), -1.0, places=10)
        self.assertAlmostEqual(kelly_fraction(1.0, 1.0), 1.0, places=10)


if __name__ == "__main__":
    unittest.main()
