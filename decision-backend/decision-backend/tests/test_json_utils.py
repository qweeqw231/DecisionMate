# -*- coding: utf-8 -*-
"""LLM 输出解析工具测试（P0-2 基础）"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import support  # noqa: F401

from agent_core.json_utils import LLMParseError, as_bool, extract_json_object  # noqa: E402


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
        with self.assertRaises(LLMParseError):
            extract_json_object('{"a": 1,}')

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
