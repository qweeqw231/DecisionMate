# -*- coding: utf-8 -*-
"""关系边界配置测试（P1-4）"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import support  # noqa: F401

import storage  # noqa: E402
import boundary_config as bc  # noqa: E402


class BoundaryConfigTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        storage.init_db()

    def setUp(self):
        bc.reset_config()


class TestDefaults(BoundaryConfigTestBase):
    def test_defaults_match_the_architecture(self):
        config = bc.load_config()
        self.assertTrue(config["enabled"])
        self.assertTrue(config["use_semantic_check"])
        # 架构 5.3.4：不记录此场景的详细数据
        self.assertTrue(config["skip_persistence"])
        self.assertIn("独立意志", config["shutdown_message"])
        self.assertTrue(config["hard_patterns"])

    def test_default_config_returns_independent_copies(self):
        first = bc.default_config()
        first["hard_patterns"].append("污染")
        self.assertNotIn("污染", bc.default_config()["hard_patterns"])

    def test_load_before_any_save_falls_back_to_defaults(self):
        self.assertEqual(bc.load_config(), bc.default_config())


class TestSaveAndLoad(BoundaryConfigTestBase):
    def test_round_trip(self):
        bc.save_config({"enabled": False, "shutdown_message": "  自定义文案  "})
        config = bc.load_config()
        self.assertFalse(config["enabled"])
        self.assertEqual(config["shutdown_message"], "自定义文案")

    def test_patterns_are_stripped_and_deduplicated(self):
        bc.save_config({"hard_patterns": ["追她", "追她", "  表白  ", "", "   "]})
        self.assertEqual(bc.load_config()["hard_patterns"], ["追她", "表白"])

    def test_partial_update_keeps_other_fields(self):
        original = bc.load_config()
        bc.save_config({"enabled": False})
        updated = bc.load_config()
        self.assertFalse(updated["enabled"])
        self.assertEqual(updated["hard_patterns"], original["hard_patterns"])
        self.assertEqual(updated["shutdown_message"], original["shutdown_message"])

    def test_updated_at_is_recorded(self):
        bc.save_config({"enabled": False})
        self.assertIsNotNone(bc.config_metadata()["updated_at"])

    def test_reset_restores_defaults(self):
        bc.save_config({"enabled": False, "hard_patterns": ["x"]})
        bc.reset_config()
        self.assertEqual(bc.load_config(), bc.default_config())


class TestValidation(BoundaryConfigTestBase):
    def test_unknown_field_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            bc.save_config({"nope": 1})
        self.assertIn("不支持的配置项", str(ctx.exception))

    def test_bad_boolean_rejected(self):
        for value in ["yes", 1, None]:
            with self.assertRaises(ValueError):
                bc.save_config({"enabled": value})

    def test_patterns_must_be_a_list_of_strings(self):
        with self.assertRaises(ValueError):
            bc.save_config({"hard_patterns": "追她"})
        with self.assertRaises(ValueError):
            bc.save_config({"hard_patterns": [123]})

    def test_pattern_length_and_count_limits(self):
        with self.assertRaises(ValueError):
            bc.save_config({"hard_patterns": ["x" * (bc.MAX_PATTERN_LENGTH + 1)]})
        with self.assertRaises(ValueError):
            bc.save_config({"hard_patterns": [f"p{i}" for i in range(bc.MAX_PATTERNS + 1)]})

    def test_empty_shutdown_message_rejected(self):
        for value in ["", "   "]:
            with self.assertRaises(ValueError):
                bc.save_config({"shutdown_message": value})

    def test_oversized_shutdown_message_rejected(self):
        with self.assertRaises(ValueError):
            bc.save_config({"shutdown_message": "x" * (bc.MAX_MESSAGE_LENGTH + 1)})


class TestCorruptedStorage(unittest.TestCase):
    """配置损坏时绝不能抛异常——边界检查在每次决策的最前面。"""

    @classmethod
    def setUpClass(cls):
        storage.init_db()

    def tearDown(self):
        bc.reset_config()

    def test_non_dict_stored_value_falls_back(self):
        storage.set_setting(bc.SETTING_KEY, ["不是对象"])
        self.assertEqual(bc.load_config(), bc.default_config())

    def test_invalid_field_falls_back_but_valid_fields_survive(self):
        storage.set_setting(bc.SETTING_KEY, {"enabled": "yes", "shutdown_message": "保留我"})
        config = bc.load_config()
        self.assertTrue(config["enabled"], "非法字段应沿用默认值")
        self.assertEqual(config["shutdown_message"], "保留我")

    def test_unparseable_stored_json_falls_back(self):
        import sqlite3
        from datetime import datetime
        conn = sqlite3.connect(storage.DB_PATH)
        conn.execute(
            "INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)",
            (bc.SETTING_KEY, "{不是 JSON", datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()
        self.assertEqual(bc.load_config(), bc.default_config())


if __name__ == "__main__":
    unittest.main()
