# -*- coding: utf-8 -*-
"""能力因子写入守卫测试（P0-1）"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import support  # noqa: F401  必须在后端模块之前导入

from factor_guard import (  # noqa: E402
    MAX_STEP, is_factor_key, is_numeric, sanitize_factor_updates, validate_new_factor,
)

PROFILE = {
    "user_id": "default",
    "考试备战能力": 0.85,
    "考试备战能力_updated_at": "2026-05-29",
    "考试备战能力_basis": "软考战损修复验证",
    "技术速通能力": 0.88,
    "风险偏好": 0.85,
}


class TestIsNumeric(unittest.TestCase):
    def test_accepts_finite_numbers(self):
        self.assertTrue(is_numeric(0.5))
        self.assertTrue(is_numeric(1))
        self.assertTrue(is_numeric(-0.2))

    def test_rejects_bool_nan_and_non_numbers(self):
        # bool 是 int 的子类，必须显式排除，否则 True 会被当成 1.0
        self.assertFalse(is_numeric(True))
        self.assertFalse(is_numeric(False))
        self.assertFalse(is_numeric(float("nan")))
        self.assertFalse(is_numeric(float("inf")))
        self.assertFalse(is_numeric("0.9"))
        self.assertFalse(is_numeric(None))


class TestIsFactorKey(unittest.TestCase):
    def test_meta_keys_are_not_factors(self):
        self.assertFalse(is_factor_key("user_id"))
        self.assertFalse(is_factor_key("考试备战能力_updated_at"))
        self.assertFalse(is_factor_key("考试备战能力_basis"))
        self.assertFalse(is_factor_key(""))
        self.assertFalse(is_factor_key(None))

    def test_real_factor_names_pass(self):
        self.assertTrue(is_factor_key("考试备战能力"))
        self.assertTrue(is_factor_key("抗压能力"))


class TestStepLimit(unittest.TestCase):
    """核心回归：单次更新幅度不得超过 ±MAX_STEP，这是原先被写坏的根因。"""

    def test_large_jump_is_clamped_to_step(self):
        accepted, _ = sanitize_factor_updates(PROFILE, {"考试备战能力": 0.99})
        self.assertAlmostEqual(accepted["考试备战能力"], 0.85 + MAX_STEP, places=4)

    def test_large_drop_is_clamped_to_step(self):
        accepted, _ = sanitize_factor_updates(PROFILE, {"技术速通能力": 0.05})
        self.assertAlmostEqual(accepted["技术速通能力"], 0.88 - MAX_STEP, places=4)

    def test_small_change_passes_through(self):
        accepted, _ = sanitize_factor_updates(PROFILE, {"考试备战能力": 0.87})
        self.assertAlmostEqual(accepted["考试备战能力"], 0.87, places=4)

    def test_repeated_extreme_proposals_move_by_at_most_one_step(self):
        """
        模拟原先的事故场景：连续多轮极端提议。

        守卫保证每轮最多移动 MAX_STEP，且始终留在 [0, 1] 内。
        注意：这限制的是「速率」而不是「累计漂移」——若模型长期单向偏移，
        因子仍会缓慢滑向边界。累计漂移属 L3（系统自校正）应审计的范畴。
        """
        profile = dict(PROFILE)
        previous = profile["技术速通能力"]
        for _ in range(20):
            accepted, _ = sanitize_factor_updates(profile, {"技术速通能力": 0.0})
            current = accepted["技术速通能力"]
            self.assertGreaterEqual(current, 0.0)
            self.assertLessEqual(current, 1.0)
            self.assertLessEqual(previous - current, MAX_STEP + 1e-9)
            profile["技术速通能力"] = current
            previous = current
        self.assertLess(profile["技术速通能力"], 0.88)

    def test_single_catastrophic_jump_is_blocked(self):
        """事故原形：模型一次性把 0.85 写成 0.28，必须被挡住。"""
        accepted, _ = sanitize_factor_updates(PROFILE, {"考试备战能力": 0.28})
        self.assertAlmostEqual(accepted["考试备战能力"], 0.80, places=4)


class TestRangeAndType(unittest.TestCase):
    def test_out_of_range_is_clamped(self):
        accepted, _ = sanitize_factor_updates(PROFILE, {"考试备战能力": 5.0})
        self.assertLessEqual(accepted["考试备战能力"], 1.0)

    def test_unknown_factor_is_rejected(self):
        accepted, rejections = sanitize_factor_updates(PROFILE, {"抗压能力": 0.8})
        self.assertNotIn("抗压能力", accepted)
        self.assertTrue(any("未知因子" in r for r in rejections))

    def test_non_numeric_value_is_rejected(self):
        accepted, rejections = sanitize_factor_updates(PROFILE, {"考试备战能力": "高"})
        self.assertNotIn("考试备战能力", accepted)
        self.assertTrue(rejections)

    def test_bool_value_is_rejected(self):
        accepted, _ = sanitize_factor_updates(PROFILE, {"考试备战能力": True})
        self.assertNotIn("考试备战能力", accepted)

    def test_nan_is_rejected(self):
        accepted, _ = sanitize_factor_updates(PROFILE, {"考试备战能力": math.nan})
        self.assertNotIn("考试备战能力", accepted)

    def test_meta_and_illegal_names_are_skipped(self):
        accepted, rejections = sanitize_factor_updates(
            PROFILE, {"user_id": 0.5, "考试备战能力_basis": "x", "考试备战能力": 0.86}
        )
        self.assertEqual(list(accepted.keys()), ["考试备战能力"])
        self.assertTrue(rejections)

    def test_non_dict_proposal_is_ignored(self):
        accepted, rejections = sanitize_factor_updates(PROFILE, ["考试备战能力"])
        self.assertEqual(accepted, {})
        self.assertTrue(rejections)

    def test_string_current_value_allows_repair(self):
        """历史脏数据（风险偏好曾是字符串 "偏激进"）应允许一次性写入合法数值。"""
        profile = {"风险偏好": "偏激进"}
        accepted, _ = sanitize_factor_updates(profile, {"风险偏好": 0.9})
        self.assertAlmostEqual(accepted["风险偏好"], 0.9, places=4)

    def test_string_current_value_still_bounded(self):
        accepted, _ = sanitize_factor_updates({"风险偏好": "偏激进"}, {"风险偏好": 9.0})
        self.assertAlmostEqual(accepted["风险偏好"], 1.0, places=4)


class TestValidateNewFactor(unittest.TestCase):
    def test_accepts_and_clamps(self):
        name, value = validate_new_factor("  抗压能力 ", 1.4)
        self.assertEqual(name, "抗压能力")
        self.assertAlmostEqual(value, 1.0, places=4)

    def test_rejects_empty_and_conflicting_names(self):
        for bad in ["", "   ", "user_id", "抗压能力_basis"]:
            with self.assertRaises(ValueError):
                validate_new_factor(bad, 0.5)

    def test_rejects_non_numeric(self):
        with self.assertRaises(ValueError):
            validate_new_factor("抗压能力", "很高")


if __name__ == "__main__":
    unittest.main()
