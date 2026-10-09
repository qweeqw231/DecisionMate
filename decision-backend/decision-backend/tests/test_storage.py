# -*- coding: utf-8 -*-
"""存储层测试（P0-5 所需的 ID 查询 + 级联删除）"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import support  # noqa: F401

import storage  # noqa: E402


class TestStorageBasics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        storage.init_db()

    def setUp(self):
        storage.clear_all_conversations()

    def _make_decision(self, conv_id, msg_id, scenario="测试场景"):
        return storage.add_decision_record(
            conv_id=conv_id, msg_id=msg_id, scenario=scenario,
            p=0.9, q=0.1, b=10.0, f_star=0.89,
            scenario_type="高赔率重注场景", loop_type="slow",
        )

    def test_tests_use_an_isolated_database(self):
        """防止误伤真实 decision.db。"""
        self.assertIn("decisionmate-tests-", storage.DB_PATH)
        self.assertNotIn("decision-backend\\decision-backend\\decision.db", storage.DB_PATH)

    def test_conversation_roundtrip(self):
        conv = storage.create_conversation()
        self.assertGreater(conv["id"], 0)
        self.assertEqual(conv["title"], "对话 #1")
        self.assertEqual(storage.get_conversation(conv["id"])["title"], "对话 #1")

    def test_messages_and_decision_binding(self):
        conv = storage.create_conversation(title="绑定测试")
        user_msg = storage.add_message(conv["id"], "user", "要不要下重注")
        assistant_msg = storage.add_message(conv["id"], "assistant", '{"f_star": 0.89}')

        decision_id = self._make_decision(conv["id"], assistant_msg["id"])
        self.assertGreater(decision_id, 0)

        record = storage.get_decision_record(decision_id)
        self.assertEqual(record["message_id"], assistant_msg["id"])
        self.assertEqual(record["conversation_id"], conv["id"])

        messages = storage.get_messages(conv["id"])
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["id"], user_msg["id"])

    def test_decision_id_lookups_for_vector_cleanup(self):
        """P0-5：删除前必须能取到决策 ID，否则无法同步清理向量。"""
        conv_a = storage.create_conversation(title="A")
        conv_b = storage.create_conversation(title="B")

        msg_a = storage.add_message(conv_a["id"], "assistant", "{}")
        msg_b = storage.add_message(conv_b["id"], "assistant", "{}")
        id_a1 = self._make_decision(conv_a["id"], msg_a["id"])
        id_a2 = self._make_decision(conv_a["id"], msg_a["id"])
        id_b = self._make_decision(conv_b["id"], msg_b["id"])

        self.assertEqual(sorted(storage.get_decision_ids_for_conversation(conv_a["id"])), sorted([id_a1, id_a2]))
        self.assertEqual(storage.get_decision_ids_for_conversation(conv_b["id"]), [id_b])
        self.assertTrue({id_a1, id_a2, id_b}.issubset(set(storage.get_all_decision_ids())))
        self.assertEqual(storage.get_decision_ids_for_conversation(999999), [])

    def test_deleting_conversation_cascades_to_decisions(self):
        conv = storage.create_conversation()
        msg = storage.add_message(conv["id"], "assistant", "{}")
        decision_id = self._make_decision(conv["id"], msg["id"])

        storage.delete_conversation(conv["id"])

        self.assertIsNone(storage.get_conversation(conv["id"]))
        self.assertIsNone(storage.get_decision_record(decision_id))
        self.assertEqual(storage.get_messages(conv["id"]), [])

    def test_clear_all_empties_everything(self):
        for _ in range(3):
            conv = storage.create_conversation()
            msg = storage.add_message(conv["id"], "assistant", "{}")
            self._make_decision(conv["id"], msg["id"])

        storage.clear_all_conversations()

        self.assertEqual(storage.get_conversations(), [])
        self.assertEqual(storage.get_all_decision_ids(), [])

    def test_fast_loop_messages_have_no_decision_record(self):
        """快回路不进 decision_records，因此不会产生向量，属预期行为。"""
        conv = storage.create_conversation()
        storage.add_message(conv["id"], "user", "今天中午吃什么")
        storage.add_message(conv["id"], "assistant", '{"loop_type": "fast"}')
        self.assertEqual(storage.get_decision_ids_for_conversation(conv["id"]), [])


if __name__ == "__main__":
    unittest.main()
