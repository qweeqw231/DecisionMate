# -*- coding: utf-8 -*-
"""关系边界 Agent 测试（P1-4）"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import support  # noqa: F401

from agent_core import boundary_agent  # noqa: E402
from agent_core.boundary_agent import check_boundary, match_hard_rules  # noqa: E402

CONFIG_WITH_SEMANTIC = {
    "enabled": True,
    "use_semantic_check": True,
    "hard_patterns": ["追她", "表白"],
    "shutdown_message": "关机文案",
    "skip_persistence": True,
}

CONFIG_RULES_ONLY = dict(CONFIG_WITH_SEMANTIC, use_semantic_check=False)
CONFIG_DISABLED = dict(CONFIG_WITH_SEMANTIC, enabled=False)


def semantic_says(is_boundary: bool, reason="语义结论"):
    """把大模型调用替换为固定判定。"""
    original = boundary_agent.chat
    calls = []

    def fake_chat(**kwargs):
        calls.append(kwargs)
        return json.dumps({"is_boundary": is_boundary, "reason": reason}, ensure_ascii=False)

    boundary_agent.chat = fake_chat
    return original, calls


class TestHardRules(unittest.TestCase):
    def test_matches_substring(self):
        self.assertEqual(match_hard_rules("我该不该追她，怎么判断", ["追她"]), "追她")

    def test_returns_none_when_no_match(self):
        self.assertIsNone(match_hard_rules("要不要花周末复盘", ["追她"]))

    def test_tolerates_bad_patterns(self):
        self.assertIsNone(match_hard_rules("随便", [None, "", "  ", 123]))
        self.assertIsNone(match_hard_rules("", ["追她"]))
        self.assertIsNone(match_hard_rules("追她", None))

    def test_first_match_wins(self):
        self.assertEqual(match_hard_rules("我要不要向她表白呢", ["向她表白", "表白"]), "向她表白")


class TestHardRuleShutdown(unittest.TestCase):
    def test_hard_rule_shuts_down_without_calling_the_model(self):
        original, calls = semantic_says(False)
        try:
            verdict = check_boundary("我该不该追她", CONFIG_WITH_SEMANTIC)
        finally:
            boundary_agent.chat = original
        self.assertTrue(verdict.is_boundary)
        self.assertEqual(verdict.category, "hard_rule")
        self.assertEqual(verdict.matched_rule, "追她")
        self.assertFalse(verdict.degraded)
        self.assertEqual(calls, [], "硬规则命中时不应再调用大模型")


class TestSemanticCheck(unittest.TestCase):
    def test_semantic_boundary_verdict(self):
        original, calls = semantic_says(True, "决策对象是某个具体的人")
        try:
            verdict = check_boundary("怎么才能让她答应和我在一起", CONFIG_WITH_SEMANTIC)
        finally:
            boundary_agent.chat = original
        self.assertTrue(verdict.is_boundary)
        self.assertEqual(verdict.category, "semantic")
        self.assertIn("具体的人", verdict.reason)
        self.assertEqual(len(calls), 1)

    def test_semantic_pass_verdict(self):
        original, _ = semantic_says(False, "这是自我审视")
        try:
            verdict = check_boundary("我现在是否适合进入一段关系", CONFIG_WITH_SEMANTIC)
        finally:
            boundary_agent.chat = original
        self.assertFalse(verdict.is_boundary)
        self.assertEqual(verdict.category, "none")
        self.assertIn("自我审视", verdict.reason)

    def test_semantic_check_can_be_disabled(self):
        original, calls = semantic_says(True)
        try:
            verdict = check_boundary("怎么才能让她答应", CONFIG_RULES_ONLY)
        finally:
            boundary_agent.chat = original
        self.assertFalse(verdict.is_boundary)
        self.assertEqual(calls, [])

    def test_disabled_protection_short_circuits_everything(self):
        original, calls = semantic_says(True)
        try:
            verdict = check_boundary("我该不该追她", CONFIG_DISABLED)
        finally:
            boundary_agent.chat = original
        self.assertFalse(verdict.is_boundary)
        self.assertEqual(calls, [])


class TestFailDirection(unittest.TestCase):
    """
    语义判定失败时**不关机**，但必须标记 degraded：
    硬规则是用户手写的确定性边界；因一次大模型抖动关掉全部场景会让系统不可用。
    """

    def test_llm_error_degrades_instead_of_shutting_down(self):
        original = boundary_agent.chat
        boundary_agent.chat = lambda **kwargs: (_ for _ in ()).throw(RuntimeError("API 超时"))
        try:
            verdict = check_boundary("怎么才能让她答应", CONFIG_WITH_SEMANTIC)
        finally:
            boundary_agent.chat = original
        self.assertFalse(verdict.is_boundary)
        self.assertTrue(verdict.degraded)
        self.assertIn("未能完成", verdict.reason)

    def test_unparseable_output_degrades(self):
        original = boundary_agent.chat
        boundary_agent.chat = lambda **kwargs: "抱歉，我无法判断。"
        try:
            verdict = check_boundary("怎么才能让她答应", CONFIG_WITH_SEMANTIC)
        finally:
            boundary_agent.chat = original
        self.assertFalse(verdict.is_boundary)
        self.assertTrue(verdict.degraded)

    def test_hard_rules_still_work_when_the_model_is_down(self):
        original = boundary_agent.chat
        boundary_agent.chat = lambda **kwargs: (_ for _ in ()).throw(RuntimeError("API 超时"))
        try:
            verdict = check_boundary("我该不该追她", CONFIG_WITH_SEMANTIC)
        finally:
            boundary_agent.chat = original
        self.assertTrue(verdict.is_boundary)
        self.assertEqual(verdict.category, "hard_rule")
        self.assertFalse(verdict.degraded)

    def test_missing_is_boundary_field_defaults_to_pass(self):
        original = boundary_agent.chat
        boundary_agent.chat = lambda **kwargs: '{"reason": "没给字段"}'
        try:
            verdict = check_boundary("某个场景", CONFIG_WITH_SEMANTIC)
        finally:
            boundary_agent.chat = original
        self.assertFalse(verdict.is_boundary)

    def test_string_false_is_not_inverted(self):
        original = boundary_agent.chat
        boundary_agent.chat = lambda **kwargs: '{"is_boundary": "false", "reason": "放行"}'
        try:
            verdict = check_boundary("某个场景", CONFIG_WITH_SEMANTIC)
        finally:
            boundary_agent.chat = original
        self.assertFalse(verdict.is_boundary)


if __name__ == "__main__":
    unittest.main()
