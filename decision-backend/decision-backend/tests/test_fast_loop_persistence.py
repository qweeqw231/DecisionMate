# -*- coding: utf-8 -*-
"""
快回路决策落库测试（P2-2）

背景：快回路决策此前完全不落库，导致 L3 的 loop_distribution 里 fast 恒为 0，
快回路的准确率与路由质量无法从真实使用数据评估。
现在快回路决策同样写入 decision_records，但用 params_available=0 标明
「没有量化参数」，任何按 f* 的统计都必须先看这个标记。
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import support  # noqa: F401

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import storage  # noqa: E402

FAST_SCENARIO = "有人插队我要不要当场制止"


class TestFastLoopPersistence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)
        cls.client.__enter__()
        storage.init_db()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def setUp(self):
        storage.clear_all_conversations()
        # 快回路只需要一次 chat 调用，用桩替代，避免真实网络请求
        self._orig_chat = main.chat
        main.chat = lambda **kwargs: json.dumps(
            {"recommendation": "当场制止，保持礼貌", "reasoning": "成本低"}, ensure_ascii=False)

    def tearDown(self):
        main.chat = self._orig_chat

    def _send_fast(self):
        conv = self.client.post("/api/conversations", json={"title": "快回路"}).json()
        resp = self.client.post(f"/api/conversations/{conv['id']}/messages",
                                json={"scenario": FAST_SCENARIO})
        self.assertEqual(resp.status_code, 200, resp.text)
        return conv["id"], resp.json()

    def test_fast_decision_is_archived(self):
        conv_id, report = self._send_fast()
        self.assertEqual(report["loop_type"], "fast")

        records = storage.get_decision_records_with_report()
        self.assertEqual(len(records), 1, "快回路决策必须落库，否则 L3 无法评估路由")
        record = records[0]
        self.assertEqual(record["loop_type"], "fast")
        self.assertEqual(record["conversation_id"], conv_id)
        self.assertEqual(record["scenario"], FAST_SCENARIO)

    def test_params_are_flagged_as_unavailable(self):
        self._send_fast()
        record = storage.get_decision_records_with_report()[0]
        self.assertEqual(record["params_available"], 0,
                         "快回路没有量化参数，必须与真实的 f*=0 区分开")

    def test_message_id_is_bound_to_the_real_message(self):
        conv_id, _ = self._send_fast()
        messages = storage.get_messages(conv_id)
        assistant = [m for m in messages if m["role"] == "assistant"][-1]
        record = storage.get_decision_records_with_report()[0]
        self.assertEqual(record["message_id"], assistant["id"])

    def test_no_vector_is_stored_for_fast_decisions(self):
        """向量元数据里的 p/b/f* 会全是 0，存进去会误导后续的历史参考。"""
        import vector_store
        self._send_fast()
        self.assertEqual(vector_store.get_all_decision_vector_ids(), [])

    def test_l1_tracker_rejects_fast_decisions(self):
        conv_id, _ = self._send_fast()
        messages = storage.get_messages(conv_id)
        msg_id = [m for m in messages if m["role"] == "assistant"][-1]["id"]

        resp = self.client.post(
            f"/api/conversations/{conv_id}/messages/{msg_id}/execution-updates",
            json={"note": "第一周完成一半"})
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertIn("快回路", resp.json()["detail"])

        self.assertEqual(
            self.client.get(
                f"/api/conversations/{conv_id}/messages/{msg_id}/execution-updates"
            ).status_code,
            400,
        )


class TestFastLoopFeedback(unittest.TestCase):
    """快回路决策现在也可以提交反馈，但复盘必须走定性路径，不调整能力因子。"""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)
        cls.client.__enter__()
        storage.init_db()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def setUp(self):
        storage.clear_all_conversations()
        self._orig_chat = main.chat
        self._orig_archive = main.run_archive
        main.chat = lambda **kwargs: json.dumps(
            {"recommendation": "当场制止", "reasoning": "成本低"}, ensure_ascii=False)

    def tearDown(self):
        main.chat = self._orig_chat
        main.run_archive = self._orig_archive

    def test_feedback_is_accepted_and_calls_the_qualitative_path(self):
        conv = self.client.post("/api/conversations", json={"title": "快回路反馈"}).json()
        self.client.post(f"/api/conversations/{conv['id']}/messages",
                         json={"scenario": FAST_SCENARIO})
        msg_id = [m for m in storage.get_messages(conv["id"])
                  if m["role"] == "assistant"][-1]["id"]

        captured = {}
        from models.schemas import ArchiveReport

        def fake_archive(**kwargs):
            captured.update(kwargs)
            return ArchiveReport(
                decision_id=kwargs["decision_id"], initial_f_star=0.0,
                feedback_type=kwargs["feedback_type"],
                deviation_analysis="定性回顾：直觉建议贴合实际。",
                factor_updates={}, new_factor_proposal=None,
                reusable_pattern="插队场景直接礼貌制止即可",
                params_available=False,
            )
        main.run_archive = fake_archive

        resp = self.client.post(
            f"/api/conversations/{conv['id']}/messages/{msg_id}/feedback",
            json={"feedback_type": "useful", "feedback_text": "确实有效"})
        self.assertEqual(resp.status_code, 200, resp.text)

        self.assertFalse(captured["params_available"],
                         "快回路复盘必须走定性路径")
        archive = resp.json()["archive_report"]
        self.assertEqual(archive["factor_updates"], {})
        self.assertIsNone(archive["new_factor_proposal"])
        self.assertFalse(archive["params_available"])

    def test_slow_decision_still_uses_the_quantitative_path(self):
        """回归：慢回路决策不能被误判成定性路径。"""
        conv = self.client.post("/api/conversations", json={"title": "慢回路"}).json()
        msg = storage.add_message(conv["id"], "assistant", "{}")
        storage.add_decision_record(
            conv_id=conv["id"], msg_id=msg["id"], scenario="要不要备考",
            p=0.9, q=0.1, b=10.0, f_star=0.89,
            scenario_type="高赔率重注场景", loop_type="slow")

        captured = {}
        from models.schemas import ArchiveReport

        def fake_archive(**kwargs):
            captured.update(kwargs)
            return ArchiveReport(decision_id=kwargs["decision_id"], initial_f_star=0.89,
                                 feedback_type=kwargs["feedback_type"],
                                 deviation_analysis="x", factor_updates={})
        main.run_archive = fake_archive

        self.client.post(f"/api/conversations/{conv['id']}/messages/{msg['id']}/feedback",
                         json={"feedback_type": "useful"})
        self.assertTrue(captured["params_available"])


if __name__ == "__main__":
    unittest.main()
