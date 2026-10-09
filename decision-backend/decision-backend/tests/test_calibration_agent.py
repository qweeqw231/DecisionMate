# -*- coding: utf-8 -*-
"""L1 执行中校准 Agent 测试"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import support  # noqa: F401

from agent_core import calibration_agent  # noqa: E402
from agent_core.calibration_agent import recalibrate, verdict_for_f_star  # noqa: E402
from kelly import kelly_fraction  # noqa: E402

INITIAL = {"p": 0.9, "q": 0.1, "b": 10.0, "f_star": 0.89}


def with_llm(output):
    """把大模型调用替换为固定输出，返回 (恢复函数, 调用记录)。"""
    original = calibration_agent.chat
    calls = []

    def fake_chat(**kwargs):
        calls.append(kwargs)
        return output

    calibration_agent.chat = fake_chat
    return original, calls


def payload(p, b, reasoning="推理说明"):
    return json.dumps({"p": p, "b": b, "reasoning": reasoning}, ensure_ascii=False)


class TestVerdictMapping(unittest.TestCase):
    """f* → 继续 / 观望 / 及时止损 的判定阈值必须与建议档位同口径。"""

    def test_continue_for_positive_bets(self):
        self.assertEqual(verdict_for_f_star(0.9), "continue")
        self.assertEqual(verdict_for_f_star(0.61), "continue")
        self.assertEqual(verdict_for_f_star(0.3), "continue")

    def test_watch_at_the_marginal_band(self):
        self.assertEqual(verdict_for_f_star(0.2), "watch")
        self.assertEqual(verdict_for_f_star(0.0), "watch")

    def test_stop_when_kelly_goes_negative(self):
        self.assertEqual(verdict_for_f_star(-0.01), "stop")
        self.assertEqual(verdict_for_f_star(-2.0), "stop")


class TestRecalibration(unittest.TestCase):
    def test_recomputes_f_star_with_the_deterministic_engine(self):
        original, calls = with_llm(payload(0.8, 4.0))
        try:
            result = recalibrate("场景", "高赔率重注场景", INITIAL, [], "第一周完成了一半")
        finally:
            calibration_agent.chat = original
        self.assertAlmostEqual(result.p, 0.8, places=4)
        self.assertAlmostEqual(result.b, 4.0, places=4)
        self.assertAlmostEqual(result.q, 0.2, places=4)
        # f* 必须等于确定性公式的结果，而不是模型给的数字
        self.assertAlmostEqual(result.f_star, round(kelly_fraction(0.8, 4.0), 4), places=6)
        self.assertEqual(result.verdict, "continue")
        self.assertFalse(result.degraded)
        self.assertEqual(len(calls), 1)

    def test_downgrade_leads_to_stop(self):
        original, _ = with_llm(payload(0.15, 0.5))
        try:
            result = recalibrate("场景", "高赔率重注场景", INITIAL, [], "关键假设被证伪，进度只有一成")
        finally:
            calibration_agent.chat = original
        self.assertLess(result.f_star, 0)
        self.assertEqual(result.verdict, "stop")
        self.assertEqual(result.advice, "主动撤出，保护核心资产")

    def test_prompt_includes_history_and_note(self):
        original, calls = with_llm(payload(0.7, 3.0))
        history = [{"note": "第一周完成 30%", "p": 0.85, "b": 8.0, "f_star": 0.83}]
        try:
            recalibrate("要不要备考", "高赔率重注场景", INITIAL, history, "第二周完成 60%")
        finally:
            calibration_agent.chat = original
        message = calls[0]["user_message"]
        self.assertIn("要不要备考", message)
        self.assertIn("第一周完成 30%", message)
        self.assertIn("第二周完成 60%", message)
        self.assertIn("初始参数", message)

    def test_fenced_json_is_tolerated(self):
        original, _ = with_llm("```json\n" + payload(0.7, 3.0) + "\n```")
        try:
            result = recalibrate("场景", "类型", INITIAL, [], "进展")
        finally:
            calibration_agent.chat = original
        self.assertFalse(result.degraded)
        self.assertAlmostEqual(result.p, 0.7, places=4)


class TestFailDirection(unittest.TestCase):
    """
    校准失败时绝不能编造新参数：执行中的仓位上，
    一个凭空生成的数字比「这次没算出来」危险得多。
    """

    def _assert_degraded(self, result, expected_p, expected_b):
        self.assertTrue(result.degraded)
        self.assertAlmostEqual(result.p, expected_p, places=4)
        self.assertAlmostEqual(result.b, expected_b, places=4)
        self.assertIn("沿用", result.reasoning)
        # 判定必须与它依据的那组（沿用的）参数自洽，不能硬编码成固定值
        self.assertEqual(result.verdict, verdict_for_f_star(result.f_star))
        self.assertAlmostEqual(result.f_star,
                               round(kelly_fraction(expected_p, expected_b), 4), places=6)

    def test_invalid_probability_is_rejected(self):
        original, _ = with_llm(payload(1.4, 3.0))
        try:
            result = recalibrate("场景", "类型", INITIAL, [], "进展")
        finally:
            calibration_agent.chat = original
        self._assert_degraded(result, 0.9, 10.0)

    def test_non_positive_odds_is_rejected(self):
        original, _ = with_llm(payload(0.7, 0.0))
        try:
            result = recalibrate("场景", "类型", INITIAL, [], "进展")
        finally:
            calibration_agent.chat = original
        self._assert_degraded(result, 0.9, 10.0)

    def test_unparseable_output_degrades(self):
        original, _ = with_llm("抱歉，我无法判断。")
        try:
            result = recalibrate("场景", "类型", INITIAL, [], "进展")
        finally:
            calibration_agent.chat = original
        self._assert_degraded(result, 0.9, 10.0)

    def test_missing_fields_degrade(self):
        original, _ = with_llm('{"p": 0.7}')
        try:
            result = recalibrate("场景", "类型", INITIAL, [], "进展")
        finally:
            calibration_agent.chat = original
        self._assert_degraded(result, 0.9, 10.0)

    def test_transport_error_degrades(self):
        original = calibration_agent.chat
        calibration_agent.chat = lambda **kwargs: (_ for _ in ()).throw(RuntimeError("API 超时"))
        try:
            result = recalibrate("场景", "类型", INITIAL, [], "进展")
        finally:
            calibration_agent.chat = original
        self._assert_degraded(result, 0.9, 10.0)

    def test_degraded_falls_back_to_last_calibration_not_initial(self):
        history = [{"note": "进度", "p": 0.6, "q": 0.4, "b": 2.0, "f_star": 0.4}]
        original, _ = with_llm("不是 JSON")
        try:
            result = recalibrate("场景", "类型", INITIAL, history, "新进展")
        finally:
            calibration_agent.chat = original
        self._assert_degraded(result, 0.6, 2.0)

    def test_non_numeric_strings_degrade(self):
        original, _ = with_llm('{"p": "很高", "b": "很大"}')
        try:
            result = recalibrate("场景", "类型", INITIAL, [], "进展")
        finally:
            calibration_agent.chat = original
        self._assert_degraded(result, 0.9, 10.0)


if __name__ == "__main__":
    unittest.main()
