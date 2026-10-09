# -*- coding: utf-8 -*-
"""LLM 输出解析工具测试（P0-2 基础）"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import support  # noqa: F401

from agent_core.json_utils import (  # noqa: E402
    LLMParseError, as_bool, extract_json_object, strip_trailing_commas,
)


class TestTrailingCommaTolerance(unittest.TestCase):
    """
    实测事故：快回路模型返回末尾带多余逗号的 JSON，
    json.loads 直接失败，于是整段原始 JSON 被当成「建议正文」渲染给用户。
    """

    def test_object_with_trailing_comma(self):
        raw = '{\n  "recommendation": "当场制止",\n  "reasoning": "成本低",\n}'
        self.assertEqual(extract_json_object(raw),
                         {"recommendation": "当场制止", "reasoning": "成本低"})

    def test_nested_array_trailing_comma(self):
        raw = '{"items": [1, 2, 3,], "ok": true}'
        self.assertEqual(extract_json_object(raw), {"items": [1, 2, 3], "ok": True})

    def test_trailing_comma_inside_a_string_is_preserved(self):
        """字符串里的「,}」不能被当成多余逗号删掉。"""
        raw = '{"text": "a,}b", "n": 1,}'
        self.assertEqual(extract_json_object(raw), {"text": "a,}b", "n": 1})

    def test_escaped_quote_does_not_confuse_the_scanner(self):
        raw = '{"text": "他说\\"好，}\\"", "n": 1,}'
        parsed = extract_json_object(raw)
        self.assertEqual(parsed["n"], 1)
        self.assertIn("好，}", parsed["text"])

    def test_fenced_json_with_trailing_comma(self):
        raw = '```json\n{"a": 1,}\n```'
        self.assertEqual(extract_json_object(raw), {"a": 1})

    def test_genuinely_broken_json_still_fails(self):
        """修补只针对多余逗号，不能把真正的语法错误也放行。"""
        with self.assertRaises(LLMParseError):
            extract_json_object('{"a": 1 "b": 2}')

    def test_strip_helper_is_a_noop_for_valid_json(self):
        raw = '{"a": [1, 2], "b": {"c": 3}}'
        self.assertEqual(strip_trailing_commas(raw), raw)

    def test_strip_helper_handles_deep_nesting(self):
        self.assertEqual(strip_trailing_commas('{"a": {"b": [1,],},}'), '{"a": {"b": [1]}}')


class TestExtractJsonObject(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(extract_json_object('{"a": 1}'), {"a": 1})

    def test_fenced_json(self):
        raw = '```json\n{"a": 1}\n```'
        self.assertEqual(extract_json_object(raw), {"a": 1})

    def test_fenced_without_language(self):
        self.assertEqual(extract_json_object('```\n{"a": 1}\n```'), {"a": 1})

    def test_prose_around_json(self):
        """旧实现只剥离开头的代码块标记，前面多一句话就整段解析失败。"""
        raw = '好的，我的评估如下：\n{"a": 1}\n以上是我的结论。'
        self.assertEqual(extract_json_object(raw), {"a": 1})

    def test_trailing_prose_after_fence(self):
        raw = '```json\n{"a": 1}\n```\n希望有帮助！'
        self.assertEqual(extract_json_object(raw), {"a": 1})

    def test_nested_object(self):
        raw = '{"outer": {"inner": [1, 2]}, "b": true}'
        self.assertEqual(extract_json_object(raw), {"outer": {"inner": [1, 2]}, "b": True})

    def test_rejects_non_object_payloads(self):
        for raw in ['[1, 2, 3]', '"just a string"', '42']:
            with self.assertRaises(LLMParseError):
                extract_json_object(raw)

    def test_rejects_empty_and_none(self):
        for raw in [None, "", "   ", "完全没有 JSON"]:
            with self.assertRaises(LLMParseError):
                extract_json_object(raw)

    def test_rejects_malformed_json(self):
        # 注意：末尾多余逗号是被刻意容忍的（见 TestTrailingCommaTolerance），
        # 这里用真正无法修补的语法错误。
        with self.assertRaises(LLMParseError):
            extract_json_object('{"a": 1 "b": 2}')
        with self.assertRaises(LLMParseError):
            extract_json_object('{"a": }')

    def test_parse_error_is_a_value_error(self):
        """调用方按 ValueError 统一捕获，必须保持这个继承关系。"""
        self.assertTrue(issubclass(LLMParseError, ValueError))


class TestAsBool(unittest.TestCase):
    def test_real_booleans(self):
        self.assertTrue(as_bool(True, default=False))
        self.assertFalse(as_bool(False, default=True))

    def test_string_false_is_false(self):
        """关键回归：bool("false") 是 True，在安全字段上会把无风险判成有风险。"""
        for token in ["false", "False", "FALSE", " false ", "0", "no", "否", "无", ""]:
            self.assertFalse(as_bool(token, default=True), msg=repr(token))

    def test_string_true_is_true(self):
        for token in ["true", "True", "1", "yes", "是"]:
            self.assertTrue(as_bool(token, default=False), msg=repr(token))

    def test_numbers(self):
        self.assertTrue(as_bool(1, default=False))
        self.assertFalse(as_bool(0, default=True))

    def test_unrecognised_falls_back_to_default(self):
        self.assertTrue(as_bool("maybe", default=True))
        self.assertFalse(as_bool("maybe", default=False))
        self.assertTrue(as_bool(None, default=True))
        self.assertFalse(as_bool(None, default=False))
        self.assertFalse(as_bool([], default=False))


if __name__ == "__main__":
    unittest.main()
