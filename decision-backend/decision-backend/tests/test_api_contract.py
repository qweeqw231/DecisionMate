# -*- coding: utf-8 -*-
"""
API 契约测试（P0-1 配套：新增因子端点必须可被真实客户端调用）

背景：/api/user-profile/add-factor 原先用裸标量参数声明，FastAPI 会把它解析成
query string，而客户端提交的是 JSON body → 恒定 422。而 factor_guard 又把
「写入未知因子」的唯一正当出口指向该接口，等于让新因子永久无法写入。
"""
import json
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


class TestSystemAuditEndpoint(unittest.TestCase):
    """L3 系统自校正：汇总审计接口必须是只读且结构完整的。"""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def test_audit_returns_expected_shape(self):
        resp = self.client.get("/api/system-audit")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        for key in ("generated_at", "window", "totals", "decision_accuracy",
                    "loop_distribution", "recommendation_mix", "by_scenario_type",
                    "by_loop_type", "trend_by_month", "quality", "mux_parameters",
                    "capability_profile", "limitations"):
            self.assertIn(key, body, f"缺少字段 {key}")
        self.assertTrue(body["limitations"], "能力边界必须随结果返回")

    def test_audit_is_read_only(self):
        """审计不得产生决策记录或消息。"""
        import storage
        before = len(storage.get_all_decision_ids())
        convs_before = len(storage.get_conversations())

        self.client.get("/api/system-audit")

        self.assertEqual(len(storage.get_all_decision_ids()), before)
        self.assertEqual(len(storage.get_conversations()), convs_before)


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


class TestReportSchemaFields(unittest.TestCase):
    """P1：报告需要携带「风险降级」与「历史参考」，前端才可能展示。"""

    def _report(self, **overrides):
        from models.schemas import DecisionReport
        payload = dict(recommendation="综合建议", f_star=0.5, risk_level="低",
                       scenario_type="高赔率重注场景", quant_opinion="", risk_opinion="",
                       calculation_detail="")
        payload.update(overrides)
        return DecisionReport(**payload)

    def test_risk_degraded_is_serialized(self):
        data = json.loads(self._report(risk_degraded=True).model_dump_json())
        self.assertTrue(data["risk_degraded"])

    def test_risk_degraded_defaults_to_false(self):
        data = json.loads(self._report().model_dump_json())
        self.assertFalse(data["risk_degraded"])

    def test_history_references_are_serialized(self):
        from models.schemas import HistoryReference
        report = self._report(history_references=[
            HistoryReference(decision_id=3, similarity=0.81,
                             scenario_type="高赔率重注场景", p=0.9, b=10.0, f_star=0.89),
        ])
        data = json.loads(report.model_dump_json())
        ref = data["history_references"][0]
        self.assertEqual(ref["decision_id"], 3)
        self.assertAlmostEqual(ref["similarity"], 0.81, places=4)
        self.assertEqual(ref["scenario_type"], "高赔率重注场景")
        self.assertAlmostEqual(ref["f_star"], 0.89, places=4)

    def test_history_references_default_to_none(self):
        data = json.loads(self._report().model_dump_json())
        self.assertIsNone(data["history_references"])

    def test_history_reference_tolerates_missing_metadata(self):
        from models.schemas import HistoryReference
        ref = HistoryReference(decision_id=9, similarity=0.6)
        data = json.loads(ref.model_dump_json())
        self.assertIsNone(data["scenario_type"])
        self.assertIsNone(data["p"])
        self.assertIsNone(data["f_star"])

    def test_history_reference_rejects_non_numeric_metadata(self):
        """Chroma metadata 是弱类型的，回传时必须经过校验而不是原样透传。"""
        from models.schemas import HistoryReference
        with self.assertRaises(Exception):
            HistoryReference(decision_id=9, similarity=0.6, p="很高")


class TestBoundaryConfigApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def setUp(self):
        import boundary_config as bc
        bc.reset_config()

    def tearDown(self):
        import boundary_config as bc
        bc.reset_config()

    def test_get_returns_current_defaults_and_timestamp(self):
        body = self.client.get("/api/boundary-config").json()
        for key in ("current", "defaults", "updated_at"):
            self.assertIn(key, body)
        self.assertTrue(body["current"]["enabled"])
        self.assertTrue(body["current"]["skip_persistence"])

    def test_update_round_trip(self):
        resp = self.client.post("/api/boundary-config",
                                json={"enabled": False, "hard_patterns": ["自定义规则"]})
        self.assertEqual(resp.status_code, 200, resp.text)
        config = resp.json()["config"]
        self.assertFalse(config["enabled"])
        self.assertEqual(config["hard_patterns"], ["自定义规则"])

        again = self.client.get("/api/boundary-config").json()["current"]
        self.assertFalse(again["enabled"])
        self.assertEqual(again["hard_patterns"], ["自定义规则"])

    def test_invalid_payload_returns_400(self):
        for payload in ({"nope": 1}, {"enabled": "yes"}, {"hard_patterns": "追她"},
                        {"shutdown_message": ""}):
            with self.subTest(payload=payload):
                resp = self.client.post("/api/boundary-config", json=payload)
                self.assertEqual(resp.status_code, 400, resp.text)

    def test_reset_restores_defaults(self):
        self.client.post("/api/boundary-config", json={"enabled": False})
        resp = self.client.post("/api/boundary-config/reset")
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertTrue(resp.json()["config"]["enabled"])

    def test_audit_exposes_the_boundary_config(self):
        """架构 6.4：伦理边界条件是「用户可调整的底层参数」之一，必须可见。"""
        audit = self.client.get("/api/system-audit").json()
        self.assertIn("boundary_config", audit)
        self.assertIn("current", audit["boundary_config"])
        self.assertIn("defaults", audit["boundary_config"])


class TestBoundaryShutdownPrivacy(unittest.TestCase):
    """
    P1-4 核心保证：命中关系边界时不做量化，且**不写入任何记录**。
    用硬规则场景（"我该不该追她"）触发，因此不会调用大模型。
    """

    BOUNDARY_SCENARIO = "我该不该追她，怎么判断成功率"

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def setUp(self):
        import boundary_config as bc
        bc.reset_config()

    def tearDown(self):
        import boundary_config as bc
        bc.reset_config()

    def test_pipeline_shuts_down_and_persists_nothing(self):
        import storage

        conv = self.client.post("/api/conversations", json={"title": "边界测试"}).json()
        decisions_before = len(storage.get_all_decision_ids())

        resp = self.client.post(f"/api/conversations/{conv['id']}/messages",
                                json={"scenario": self.BOUNDARY_SCENARIO})
        self.assertEqual(resp.status_code, 200, resp.text)
        report = resp.json()

        self.assertEqual(report["loop_type"], "boundary")
        self.assertIn("独立意志", report["shutdown_message"])
        self.assertFalse(report["persisted"])
        self.assertEqual(report["category"], "hard_rule")
        self.assertIn("未写入", report["note"])

        # 隐私保证：消息、决策记录都没有落库
        self.assertEqual(storage.get_messages(conv["id"]), [],
                         "边界场景不得写入消息")
        self.assertEqual(len(storage.get_all_decision_ids()), decisions_before,
                         "边界场景不得写入决策记录")

    def test_stream_endpoint_emits_boundary_stage_and_result(self):
        conv = self.client.post("/api/conversations", json={"title": "边界流式"}).json()
        resp = self.client.post(f"/api/conversations/{conv['id']}/messages/stream",
                                json={"scenario": self.BOUNDARY_SCENARIO})
        self.assertEqual(resp.status_code, 200, resp.text)
        # SSE 的事件类型是 stage，阶段名在 data 里
        self.assertIn('"stage": "boundary"', resp.text)
        self.assertIn("event: result", resp.text)
        self.assertIn('"loop_type": "boundary"', resp.text)

    def test_non_boundary_scenario_is_not_intercepted(self):
        """正常场景不得被边界规则误伤。关闭语义判定以保证测试不访问网络。"""
        import storage
        import boundary_config as bc
        from agent_core.boundary_agent import check_boundary

        self.client.post("/api/boundary-config", json={"use_semantic_check": False})
        conv = self.client.post("/api/conversations", json={"title": "非边界"}).json()

        verdict = check_boundary("要不要花周末做深度复盘", bc.load_config())
        self.assertFalse(verdict.is_boundary)
        self.assertEqual(verdict.category, "none")
        # 未发消息，自然没有记录（确认该接口本身不产生副作用）
        self.assertEqual(storage.get_messages(conv["id"]), [])

    def test_disabling_skip_persistence_records_the_scenario(self):
        """用户显式关闭隐私保护时，边界场景按常规落库（配置生效）。"""
        import storage
        self.client.post("/api/boundary-config", json={"skip_persistence": False})
        conv = self.client.post("/api/conversations", json={"title": "记录边界"}).json()

        resp = self.client.post(f"/api/conversations/{conv['id']}/messages",
                                json={"scenario": self.BOUNDARY_SCENARIO})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertTrue(resp.json()["persisted"])
        self.assertEqual(len(storage.get_messages(conv["id"])), 2)


class TestExecutionTrajectoryApi(unittest.TestCase):
    """
    L1 执行中校准的接口契约。

    大模型调用（recalibrate / assess）一律替换为确定性桩，
    这样断言的是「系统在给定校准输入下做了什么」，而不是模型这次答得怎么样。
    """

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def setUp(self):
        import storage
        storage.clear_all_conversations()

    # ---------- 桩 ----------
    def _fake_calibration(self, p=0.8, b=4.0, degraded=False):
        from kelly import kelly_fraction
        from models.schemas import CalibrationResult
        f_star = round(kelly_fraction(p, b), 4)

        def fake(*args, **kwargs):
            return CalibrationResult(
                p=p, q=round(1 - p, 4), b=b, f_star=f_star,
                verdict="continue", advice="适度投入",
                reasoning="桩：据此重估", degraded=degraded,
            )
        return fake

    def _fake_risk(self, bankruptcy=False, level="低"):
        from models.schemas import RiskResult

        def fake(scenario, quant_result):
            return RiskResult(risk_level=level, bankruptcy_risk=bankruptcy,
                              overload_signal=False, zoh_recommend=False,
                              suggestion="桩：风险说明")
        return fake

    def _patch(self, calibration=None, risk=None):
        self._orig = (main.recalibrate, main.assess)
        if calibration is not None:
            main.recalibrate = calibration
        if risk is not None:
            main.assess = risk

    def _unpatch(self):
        main.recalibrate, main.assess = self._orig

    # ---------- 夹具 ----------
    def _decision(self, p=0.9, q=0.1, b=10.0, f_star=0.89):
        import storage
        conv = self.client.post("/api/conversations", json={"title": "L1 测试"}).json()
        msg = storage.add_message(conv["id"], "assistant", "{}")
        storage.add_decision_record(
            conv_id=conv["id"], msg_id=msg["id"], scenario="要不要花周末复盘备考",
            p=p, q=q, b=b, f_star=f_star,
            scenario_type="高赔率重注场景", loop_type="slow",
        )
        return conv["id"], msg["id"]

    def _post(self, conv_id, msg_id, note="第一周完成了一半"):
        return self.client.post(
            f"/api/conversations/{conv_id}/messages/{msg_id}/execution-updates",
            json={"note": note},
        )

    # ---------- 用例 ----------
    def test_trajectory_starts_with_the_initial_prediction(self):
        conv_id, msg_id = self._decision()
        resp = self.client.get(
            f"/api/conversations/{conv_id}/messages/{msg_id}/execution-updates")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(len(body["points"]), 1)
        point = body["points"][0]
        self.assertEqual(point["kind"], "initial")
        self.assertAlmostEqual(point["p"], 0.9, places=4)
        # 初始点两个 f* 都取决策记录中的实际建议值——
        # 多分身链路下 kelly(加权 p, 加权 b) 与记录的加权 f* 不相等，
        # 在这里「重算」会凭空造出一个从未展示给用户的数字。
        self.assertAlmostEqual(point["f_star"], 0.89, places=4)
        self.assertAlmostEqual(point["adjusted_f_star"], 0.89, places=4)

    def test_initial_point_uses_the_recorded_value_even_when_it_differs_from_kelly(self):
        """
        复现多分身场景：记录 p=0.75/b=3.3（kelly→0.679），但记录的加权 f* 是 0.643。
        初始点必须显示 0.643，而不是重算出来的 0.679。
        """
        conv_id, msg_id = self._decision(p=0.75, q=0.25, b=3.3, f_star=0.6432)
        point = self.client.get(
            f"/api/conversations/{conv_id}/messages/{msg_id}/execution-updates"
        ).json()["points"][0]
        self.assertAlmostEqual(point["f_star"], 0.6432, places=4)
        self.assertAlmostEqual(point["adjusted_f_star"], 0.6432, places=4)

    def test_post_records_an_update_and_returns_two_points(self):
        conv_id, msg_id = self._decision()
        self._patch(calibration=self._fake_calibration(), risk=self._fake_risk())
        try:
            resp = self._post(conv_id, msg_id, note="第一周完成一半")
        finally:
            self._unpatch()
        self.assertEqual(resp.status_code, 200, resp.text)
        points = resp.json()["points"]
        self.assertEqual([p["kind"] for p in points], ["initial", "calibration"])

        latest = points[-1]
        self.assertEqual(latest["note"], "第一周完成一半")
        self.assertAlmostEqual(latest["p"], 0.8, places=4)
        # f* 必须由确定性引擎算，而不是模型给的
        self.assertAlmostEqual(latest["f_star"], round(0.8 - 0.2 / 4.0, 4), places=4)
        self.assertEqual(latest["verdict"], "continue")

    def test_trajectory_grows_with_each_update(self):
        conv_id, msg_id = self._decision()
        self._patch(calibration=self._fake_calibration(), risk=self._fake_risk())
        try:
            self._post(conv_id, msg_id, "第一次进展")
            self._post(conv_id, msg_id, "第二次进展")
            resp = self._post(conv_id, msg_id, "第三次进展")
        finally:
            self._unpatch()
        points = resp.json()["points"]
        self.assertEqual(len(points), 4)
        self.assertEqual(
            [p["note"] for p in points[1:]],
            ["第一次进展", "第二次进展", "第三次进展"],
        )

    def test_survival_constraint_is_applied_to_the_calibrated_f_star(self):
        """架构 4.2 原则四：L1 给出的建议同样要过破产风险校验。"""
        conv_id, msg_id = self._decision()
        # p=0.6, b=4.5 → f*≈0.511（刚过 0.5 的重注线）
        self._patch(calibration=self._fake_calibration(p=0.6, b=4.5),
                    risk=self._fake_risk(bankruptcy=True, level="高"))
        try:
            resp = self._post(conv_id, msg_id)
        finally:
            self._unpatch()
        latest = resp.json()["points"][-1]
        self.assertAlmostEqual(latest["f_star"], 0.5111, places=4)
        self.assertAlmostEqual(latest["adjusted_f_star"], round(0.5111 * 0.3, 4), places=3)
        self.assertTrue(latest["conflict"])
        self.assertEqual(latest["risk_level"], "高")

    def test_verdict_is_derived_from_the_arbitrated_value(self):
        """
        降仓后落在「观望」区间时，判定必须跟着变——
        否则会出现「建议被动过、执行判定还是继续」的自相矛盾。
        0.5111 原始判定是 continue，降仓到 0.153 后应为 watch。
        """
        conv_id, msg_id = self._decision()
        self._patch(calibration=self._fake_calibration(p=0.6, b=4.5),
                    risk=self._fake_risk(bankruptcy=True, level="高"))
        try:
            resp = self._post(conv_id, msg_id)
        finally:
            self._unpatch()
        latest = resp.json()["points"][-1]
        self.assertLess(latest["adjusted_f_star"], 0.2)
        self.assertEqual(latest["verdict"], "watch")
        self.assertEqual(latest["advice"], "观望或小注试探")

    def test_stop_verdict_when_calibration_turns_negative(self):
        conv_id, msg_id = self._decision()
        self._patch(calibration=self._fake_calibration(p=0.15, b=0.5),
                    risk=self._fake_risk())
        try:
            resp = self._post(conv_id, msg_id)
        finally:
            self._unpatch()
        latest = resp.json()["points"][-1]
        self.assertLess(latest["f_star"], 0)
        self.assertEqual(latest["verdict"], "stop")
        self.assertEqual(latest["advice"], "主动撤出，保护核心资产")

    def test_degraded_calibration_is_recorded_and_flagged(self):
        """
        校准失败时：参数沿用上一次，degraded 如实标记，
        而判定仍按它依据的那组参数推出——不能硬编码成观察。
        """
        conv_id, msg_id = self._decision()
        # 桩返回 p=0.8,b=4.0（f*=0.75），degraded=True
        self._patch(calibration=self._fake_calibration(degraded=True),
                    risk=self._fake_risk())
        try:
            resp = self._post(conv_id, msg_id)
        finally:
            self._unpatch()
        latest = resp.json()["points"][-1]
        self.assertTrue(latest["degraded"])
        self.assertAlmostEqual(latest["f_star"], 0.75, places=4)
        self.assertEqual(latest["verdict"], "continue")

        # 落库后再取一次，标记不能丢
        again = self.client.get(
            f"/api/conversations/{conv_id}/messages/{msg_id}/execution-updates").json()
        self.assertTrue(again["points"][-1]["degraded"])

    def test_updates_are_persisted_between_requests(self):
        conv_id, msg_id = self._decision()
        self._patch(calibration=self._fake_calibration(), risk=self._fake_risk())
        try:
            self._post(conv_id, msg_id, "已记录")
        finally:
            self._unpatch()
        resp = self.client.get(
            f"/api/conversations/{conv_id}/messages/{msg_id}/execution-updates")
        self.assertEqual(len(resp.json()["points"]), 2)

    # ---------- 校验 ----------
    def test_empty_note_is_rejected(self):
        conv_id, msg_id = self._decision()
        for note in ("", "   ", "\n"):
            with self.subTest(note=note):
                resp = self._post(conv_id, msg_id, note)
                self.assertEqual(resp.status_code, 400, resp.text)

    def test_oversized_note_is_rejected(self):
        conv_id, msg_id = self._decision()
        resp = self._post(conv_id, msg_id, "x" * (main.MAX_EXECUTION_NOTE_LENGTH + 1))
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_unknown_message_returns_404(self):
        import storage
        conv = self.client.post("/api/conversations", json={"title": "无决策"}).json()
        resp = self._post(conv["id"], 999999)
        self.assertEqual(resp.status_code, 404, resp.text)
        self.assertEqual(
            self.client.get(
                f"/api/conversations/{conv['id']}/messages/999999/execution-updates"
            ).status_code,
            404,
        )
        self.assertEqual(storage.get_all_decision_ids(), [])

    def test_validation_rejects_before_calling_the_model(self):
        """参数校验必须发生在调用大模型之前，避免白花钱。"""
        conv_id, msg_id = self._decision()
        calls = []
        self._patch(calibration=lambda *a, **k: calls.append(a) or None,
                    risk=self._fake_risk())
        try:
            resp = self._post(conv_id, msg_id, "   ")
        finally:
            self._unpatch()
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
