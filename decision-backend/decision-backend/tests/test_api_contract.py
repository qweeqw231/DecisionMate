# -*- coding: utf-8 -*-
"""
API 契约测试（P0-1 配套：新增因子端点必须可被真实客户端调用）

背景：/api/user-profile/add-factor 原先用裸标量参数声明，FastAPI 会把它解析成
query string，而客户端提交的是 JSON body → 恒定 422。而 factor_guard 又把
「写入未知因子」的唯一正当出口指向该接口，等于让新因子永久无法写入。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import support  # noqa: F401

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402


class TestAddFactorContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def test_openapi_declares_a_json_request_body(self):
        """回归：端点必须接收 JSON 请求体，而不是 query string。"""
        schema = self.client.get("/openapi.json").json()
        operation = schema["paths"]["/api/user-profile/add-factor"]["post"]
        self.assertIn("requestBody", operation)
        body_schema = operation["requestBody"]["content"]["application/json"]["schema"]
        self.assertIn("AddFactorRequest", str(body_schema))

    def test_json_body_is_accepted(self):
        resp = self.client.post(
            "/api/user-profile/add-factor",
            json={"factor_name": "抗压能力", "value": 0.8, "basis": "连续3次高压场景表现优于预估"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["factor_name"], "抗压能力")
        self.assertAlmostEqual(payload["value"], 0.8, places=4)

        profile = self.client.get("/api/user-profile").json()
        self.assertAlmostEqual(profile["抗压能力"], 0.8, places=4)
        self.assertIn("抗压能力_basis", profile)

    def test_query_style_call_no_longer_works(self):
        """确认契约已切换为 JSON body（旧的 query 形式不再被接受）。"""
        resp = self.client.post(
            "/api/user-profile/add-factor?factor_name=查询因子&value=0.5&basis=x"
        )
        self.assertEqual(resp.status_code, 422)

    def test_out_of_range_value_is_clamped(self):
        resp = self.client.post(
            "/api/user-profile/add-factor",
            json={"factor_name": "越界因子", "value": 5.0},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertAlmostEqual(resp.json()["value"], 1.0, places=4)

    def test_empty_name_is_rejected_with_400(self):
        resp = self.client.post(
            "/api/user-profile/add-factor",
            json={"factor_name": "   ", "value": 0.5},
        )
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_reserved_name_is_rejected_with_400(self):
        resp = self.client.post(
            "/api/user-profile/add-factor",
            json={"factor_name": "user_id", "value": 0.5},
        )
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_non_numeric_value_is_rejected_by_validation(self):
        resp = self.client.post(
            "/api/user-profile/add-factor",
            json={"factor_name": "抗压能力", "value": "很高"},
        )
        self.assertEqual(resp.status_code, 422)


class TestConversationDeletePurgesVectors(unittest.TestCase):
    """P0-5 契约：删除对话/清空数据时必须同步清理向量。"""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def _conversation_with_decision(self):
        """建一个带决策记录的对话，使清理列表非空（空列表会被提前返回）。"""
        import storage
        conv = self.client.post("/api/conversations", json={"title": "purge 测试"}).json()
        msg = storage.add_message(conv["id"], "assistant", "{}")
        decision_id = storage.add_decision_record(
            conv_id=conv["id"], msg_id=msg["id"], scenario="场景",
            p=0.9, q=0.1, b=10.0, f_star=0.89,
            scenario_type="测试", loop_type="slow",
        )
        return conv["id"], decision_id

    def test_delete_conversation_purges_its_decision_vectors(self):
        conv_id, decision_id = self._conversation_with_decision()

        calls = []
        original = main.delete_decision_vectors
        main.delete_decision_vectors = lambda ids: (calls.append(list(ids)), len(list(ids)))[1]
        try:
            resp = self.client.delete(f"/api/conversations/{conv_id}")
        finally:
            main.delete_decision_vectors = original

        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(calls, [[decision_id]])

    def test_clear_all_purges_all_decision_vectors(self):
        _, decision_id = self._conversation_with_decision()

        calls = []
        original = main.delete_decision_vectors
        main.delete_decision_vectors = lambda ids: (calls.append(list(ids)), len(list(ids)))[1]
        try:
            resp = self.client.delete("/api/conversations")
        finally:
            main.delete_decision_vectors = original

        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(len(calls), 1)
        self.assertIn(decision_id, calls[0])


if __name__ == "__main__":
    unittest.main()
