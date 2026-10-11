# -*- coding: utf-8 -*-
"""
请求体校验测试（P2-1）

此前这些字段都是裸 str / List[dict]：空白场景会一路送进大模型并落库，
activated_personas 是未类型化的 dict，键名写错或缺字段会在管线里抛 KeyError → 500。
现在非法输入一律在请求模型层被拒（422），不会进入业务逻辑。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import support  # noqa: F401

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from models.schemas import MAX_SCENARIO_LENGTH  # noqa: E402


class TestScenarioValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def _conversation(self):
        return self.client.post("/api/conversations", json={"title": "校验测试"}).json()["id"]

    def test_empty_scenario_is_rejected(self):
        conv_id = self._conversation()
        for scenario in ("", "   ", "\n\t"):
            with self.subTest(scenario=scenario):
                resp = self.client.post(f"/api/conversations/{conv_id}/messages",
                                        json={"scenario": scenario})
                self.assertEqual(resp.status_code, 422, resp.text)

    def test_oversized_scenario_is_rejected(self):
        conv_id = self._conversation()
        resp = self.client.post(f"/api/conversations/{conv_id}/messages",
                                json={"scenario": "x" * (MAX_SCENARIO_LENGTH + 1)})
        self.assertEqual(resp.status_code, 422, resp.text)

    def test_missing_scenario_is_rejected(self):
        conv_id = self._conversation()
        resp = self.client.post(f"/api/conversations/{conv_id}/messages", json={})
        self.assertEqual(resp.status_code, 422, resp.text)

    def test_scenario_is_stripped_before_use(self):
        from models.schemas import MessageCreate
        body = MessageCreate(scenario="  要不要复盘  ")
        self.assertEqual(body.scenario, "要不要复盘")


class TestActivatedPersonasValidation(unittest.TestCase):
    """
    回归：activated_personas 原为 List[dict]，以下输入都会在管线里
    抛 KeyError 变成 500，现在必须在请求层被拒。
    """

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def _post(self, personas):
        conv_id = self.client.post("/api/conversations", json={"title": "分身校验"}).json()["id"]
        return self.client.post(
            f"/api/conversations/{conv_id}/messages",
            json={"scenario": "要不要花周末复盘备考", "activated_personas": personas},
        )

    def test_missing_keys_are_rejected_not_500(self):
        for personas in ([{"persona_id": 1}], [{"normalized_weight": 0.5}], [{}]):
            with self.subTest(personas=personas):
                resp = self._post(personas)
                self.assertEqual(resp.status_code, 422, resp.text)

    def test_wrong_key_names_are_rejected_not_500(self):
        resp = self._post([{"id": 1, "weight": 0.5}])
        self.assertEqual(resp.status_code, 422, resp.text)

    def test_non_numeric_persona_id_is_rejected(self):
        resp = self._post([{"persona_id": "第一个", "normalized_weight": 0.5}])
        self.assertEqual(resp.status_code, 422, resp.text)

    def test_weight_out_of_range_is_rejected(self):
        """前端会归一化，但仍要挡住 1e9 这类越界权重（曾可主导融合）。"""
        for weight in (1.5, -0.1, 1e9):
            with self.subTest(weight=weight):
                resp = self._post([{"persona_id": 1, "normalized_weight": weight}])
                self.assertEqual(resp.status_code, 422, resp.text)

    def test_null_is_still_accepted(self):
        """不传分身时走降级路径，这是合法用法；此处只断言不是 422（会调用大模型故不实际发送）。"""
        from models.schemas import MessageCreate
        self.assertIsNone(MessageCreate(scenario="场景").activated_personas)


class TestFeedbackValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def test_feedback_type_is_an_enum(self):
        conv_id = self.client.post("/api/conversations", json={"title": "反馈校验"}).json()["id"]
        for value in ("", "maybe", "有用", "USEFUL"):
            with self.subTest(value=value):
                resp = self.client.post(
                    f"/api/conversations/{conv_id}/messages/1/feedback",
                    json={"feedback_type": value},
                )
                self.assertEqual(resp.status_code, 422, resp.text)

    def test_oversized_feedback_text_is_rejected(self):
        conv_id = self.client.post("/api/conversations", json={"title": "反馈校验2"}).json()["id"]
        resp = self.client.post(
            f"/api/conversations/{conv_id}/messages/1/feedback",
            json={"feedback_type": "custom", "feedback_text": "x" * 3000},
        )
        self.assertEqual(resp.status_code, 422, resp.text)


class TestOtherBodyValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def test_conversation_title_cannot_be_blank(self):
        created = self.client.post("/api/conversations", json={"title": "正常"}).json()
        resp = self.client.post(f"/api/conversations/{created['id']}/rename",
                                json={"title": "   "})
        self.assertEqual(resp.status_code, 422, resp.text)

    def test_persona_name_cannot_be_blank(self):
        resp = self.client.post("/api/personas",
                                json={"name": "  ", "risk_preference": "neutral"})
        self.assertEqual(resp.status_code, 422, resp.text)

    def test_persona_risk_preference_is_an_enum(self):
        resp = self.client.post("/api/personas",
                                json={"name": "测试分身", "risk_preference": "随便"})
        self.assertEqual(resp.status_code, 422, resp.text)

    def test_persona_weight_out_of_range_is_rejected(self):
        resp = self.client.post("/api/personas/1/update", json={"weight": 5.0})
        self.assertEqual(resp.status_code, 422, resp.text)

    def test_conversation_title_is_stripped(self):
        created = self.client.post("/api/conversations", json={"title": "  留白  "}).json()
        self.assertEqual(created["title"], "留白")


if __name__ == "__main__":
    unittest.main()
