# -*- coding: utf-8 -*-
"""风险监控 Agent 测试（P0-2：解析失败必须 fail-safe）"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import support  # noqa: F401

from agent_core import risk_agent  # noqa: E402
from models.schemas import QuantResult  # noqa: E402

QUANT = QuantResult(p=0.9, q=0.1, b=10.0, f_star=0.89,
                    scenario_type="高赔率重注场景", reasoning="测试")


def assess_with(fake_output):
    """把 LLM 调用替换为固定输出，只测试解析与降级逻辑。"""
    original = risk_agent.chat
    risk_agent.chat = lambda **kwargs: fake_output
    try:
        return risk_agent.assess("测试场景", QUANT)
    finally:
        risk_agent.chat = original


class TestNormalParsing(unittest.TestCase):
    def test_valid_json(self):
        result = assess_with(
            '{"risk_level": "中", "bankruptcy_risk": true, "overload_signal": true,'
            ' "zoh_recommend": false, "suggestion": "注意休息"}'
        )
        self.assertEqual(result.risk_level, "中")
        self.assertTrue(result.bankruptcy_risk)
        self.assertTrue(result.overload_signal)
        self.assertFalse(result.zoh_recommend)
        self.assertFalse(result.degraded)

    def test_string_booleans_are_not_inverted(self):
        """关键回归：字符串 "false" 必须解析为 False。"""
        result = assess_with(
            '{"risk_level": "低", "bankruptcy_risk": "false", "overload_signal": "false",'
            ' "zoh_recommend": "false", "suggestion": "无风险"}'
        )
        self.assertFalse(result.bankruptcy_risk)
        self.assertFalse(result.overload_signal)
        self.assertEqual(result.risk_level, "低")

    def test_prose_wrapped_json(self):
        result = assess_with(
            '我的评估：\n{"risk_level": "低", "bankruptcy_risk": false,'
            ' "overload_signal": false, "zoh_recommend": false, "suggestion": "ok"}\n以上。'
        )
        self.assertEqual(result.risk_level, "低")
        self.assertFalse(result.degraded)

    def test_illegal_risk_level_is_treated_conservatively(self):
        result = assess_with(
            '{"risk_level": "极高", "bankruptcy_risk": false, "overload_signal": false,'
            ' "zoh_recommend": false, "suggestion": "x"}'
        )
        self.assertEqual(result.risk_level, "高")

    def test_missing_bankruptcy_field_defaults_conservative(self):
        result = assess_with('{"risk_level": "低", "suggestion": "x"}')
        self.assertTrue(result.bankruptcy_risk)


class TestFailSafe(unittest.TestCase):
    """P0 核心：原先解析失败返回 risk_level="低" / bankruptcy_risk=False（fail-open）。"""

    def _assert_fail_safe(self, result):
        self.assertTrue(result.degraded, "降级必须被标记，否则用户会把降级当成真实评估")
        self.assertEqual(result.risk_level, "高")
        self.assertTrue(result.bankruptcy_risk)
        self.assertIn("复核", result.suggestion)

    def test_garbage_output(self):
        self._assert_fail_safe(assess_with("抱歉，我无法完成这个任务。"))

    def test_empty_output(self):
        self._assert_fail_safe(assess_with(""))

    def test_none_output(self):
        self._assert_fail_safe(assess_with(None))

    def test_malformed_json(self):
        self._assert_fail_safe(assess_with('{"risk_level": "低", '))

    def test_json_array_payload(self):
        """旧实现里 JSON 数组能通过 json.loads，随后 data["risk_level"] 抛 TypeError 未被捕获。"""
        self._assert_fail_safe(assess_with('[{"risk_level": "低"}]'))

    def test_llm_transport_exception_also_fails_safe(self):
        original = risk_agent.chat

        def boom(**kwargs):
            raise RuntimeError("API 超时")

        risk_agent.chat = boom
        try:
            with self.assertRaises(RuntimeError):
                risk_agent.assess("场景", QUANT)
        finally:
            risk_agent.chat = original


if __name__ == "__main__":
    unittest.main()
