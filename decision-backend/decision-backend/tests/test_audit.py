# -*- coding: utf-8 -*-
"""L3 系统自校正汇总审计测试"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import support  # noqa: F401

from agent_core.mux import SURVIVAL_CLAMP_FACTOR  # noqa: E402
from audit import (  # noqa: E402
    build_system_audit, classify_f_star, expected_pre_arbitration_f_star,
    looks_survival_clamped,
)


def rec(**overrides):
    base = {
        "id": 1, "conversation_id": 1, "message_id": 1, "scenario": "场景",
        "p": 0.9, "q": 0.1, "b": 10.0, "f_star": 0.89, "scenario_type": "高赔率重注场景",
        "loop_type": "slow", "feedback_type": None, "feedback_text": None,
        "created_at": "2026-05-30T01:00:00", "report_json": None,
    }
    base.update(overrides)
    return base


def report(**overrides):
    base = {
        "loop_type": "slow", "risk_level": "低", "f_star": 0.89,
        "scenario_type": "高赔率重注场景",
        "scene_result": {"scene_recognized": False},
        "conflict_detected": False,
    }
    base.update(overrides)
    return json.dumps(base, ensure_ascii=False)


class TestHelpers(unittest.TestCase):
    def test_classify_f_star_bands(self):
        self.assertEqual(classify_f_star(0.9), "重注")
        self.assertEqual(classify_f_star(0.51), "重注")
        self.assertEqual(classify_f_star(0.5), "适度投入")
        self.assertEqual(classify_f_star(0.21), "适度投入")
        self.assertEqual(classify_f_star(0.2), "观望或小注")
        self.assertEqual(classify_f_star(0.0), "观望或小注")
        self.assertEqual(classify_f_star(-0.3), "做空/撤出")
        self.assertEqual(classify_f_star(None), "未知")

    def test_expected_f_star_single_persona_is_kelly(self):
        self.assertAlmostEqual(
            expected_pre_arbitration_f_star(rec(p=0.9, q=0.1, b=10.0), None),
            0.89, places=6)

    def test_expected_f_star_multi_persona_is_weighted(self):
        payload = {"persona_results": [
            {"f_star": 0.9, "weight": 0.5},
            {"f_star": 0.5, "weight": 0.3},
            {"f_star": 0.1, "weight": 0.2},
        ]}
        expected = 0.9 * 0.5 + 0.5 * 0.3 + 0.1 * 0.2
        self.assertAlmostEqual(
            expected_pre_arbitration_f_star(rec(), payload), expected, places=6)

    def test_expected_f_star_handles_bad_input(self):
        self.assertIsNone(expected_pre_arbitration_f_star(rec(b=0), None))
        self.assertIsNone(expected_pre_arbitration_f_star(rec(p=None), None))

    def test_empty_persona_list_falls_back_to_kelly(self):
        """没有分身数据时退回凯利原始值，而不是判定为无法推算。"""
        self.assertAlmostEqual(
            expected_pre_arbitration_f_star(rec(p=0.9, q=0.1, b=10.0),
                                           {"persona_results": []}),
            0.89, places=6)

    def test_persona_entries_with_unusable_numbers_are_skipped(self):
        payload = {"persona_results": [
            {"f_star": 0.9, "weight": 0.5},
            {"f_star": None, "weight": "x"},
            "不是字典",
        ]}
        self.assertAlmostEqual(
            expected_pre_arbitration_f_star(rec(), payload), 0.9, places=6)

    def test_survival_clamp_detection(self):
        # 仲裁前 0.9，记录值恰为 0.9 × 0.3 → 判定为被硬约束下调
        self.assertTrue(looks_survival_clamped(0.9, 0.9 * SURVIVAL_CLAMP_FACTOR))
        # 未被下调
        self.assertFalse(looks_survival_clamped(0.9, 0.9))
        # 仲裁前不高，不适用硬约束
        self.assertFalse(looks_survival_clamped(0.3, 0.09))
        self.assertFalse(looks_survival_clamped(None, 0.3))


class TestEmptyAndDegenerate(unittest.TestCase):
    def test_empty_dataset(self):
        audit = build_system_audit(records=[])
        self.assertEqual(audit["totals"]["decisions"], 0)
        self.assertIsNone(audit["decision_accuracy"]["value"])
        self.assertIsNone(audit["avg_f_star"])
        self.assertIsNone(audit["window"]["start"])
        self.assertEqual(audit["by_scenario_type"], [])
        self.assertIsNone(audit["quality"]["conflict_rate"])

    def test_accuracy_is_none_not_zero_without_feedback(self):
        audit = build_system_audit(records=[rec(report_json=report())])
        self.assertEqual(audit["decision_accuracy"]["sample"], 0)
        self.assertIsNone(audit["decision_accuracy"]["value"],
                          "无反馈样本时必须是 None，不能谎报为 0%")

    def test_missing_report_is_counted_not_fatal(self):
        audit = build_system_audit(records=[rec(report_json=None), rec(report_json=report())])
        self.assertEqual(audit["totals"]["reports_missing"], 1)
        self.assertEqual(audit["totals"]["decisions"], 2)

    def test_unparseable_and_non_dict_reports(self):
        audit = build_system_audit(records=[
            rec(report_json="{不是 JSON"),   # 语法错误
            rec(report_json="[1, 2, 3]"),    # 合法 JSON 但顶层不是对象
            rec(report_json=""),             # 空内容
        ])
        # 三者都无法解析出报告；它们不算「缺失」（raw 不为 None）
        self.assertEqual(audit["totals"]["reports_unparseable"], 3)
        self.assertEqual(audit["totals"]["reports_missing"], 0)
        self.assertEqual(audit["quality"]["reports_usable"], 0)


class TestAggregation(unittest.TestCase):
    def test_feedback_and_accuracy(self):
        records = [
            rec(feedback_type="useful", report_json=report()),
            rec(feedback_type="useful", report_json=report()),
            rec(feedback_type="inaccurate", report_json=report()),
            rec(feedback_type=None, report_json=report()),
        ]
        audit = build_system_audit(records=records)
        self.assertEqual(audit["totals"]["with_feedback"], 3)
        self.assertAlmostEqual(audit["decision_accuracy"]["value"], 2 / 3, places=4)
        self.assertAlmostEqual(audit["totals"]["feedback_coverage"], 0.75, places=4)

    def test_breakdown_by_scenario_type(self):
        records = [
            rec(scenario_type="高赔率重注场景", feedback_type="useful", report_json=report()),
            rec(scenario_type="高赔率重注场景", feedback_type="inaccurate", report_json=report()),
            rec(scenario_type="低赔率做空/休整场景", feedback_type="useful", report_json=report()),
        ]
        audit = build_system_audit(records=records)
        rows = {row["key"]: row for row in audit["by_scenario_type"]}
        self.assertEqual(rows["高赔率重注场景"]["decisions"], 2)
        self.assertAlmostEqual(rows["高赔率重注场景"]["accuracy"], 0.5, places=4)
        self.assertAlmostEqual(rows["低赔率做空/休整场景"]["accuracy"], 1.0, places=4)
        # 排序：决策多的在前
        self.assertEqual(audit["by_scenario_type"][0]["key"], "高赔率重注场景")

    def test_blank_scenario_type_is_grouped_explicitly(self):
        audit = build_system_audit(records=[rec(scenario_type="", report_json=report())])
        self.assertEqual(audit["by_scenario_type"][0]["key"], "（未识别）")

    def test_recommendation_mix_and_ratio(self):
        records = [
            rec(f_star=0.9, report_json=report()),
            rec(f_star=0.3, report_json=report()),
            rec(f_star=-0.2, report_json=report()),
            rec(f_star=0.1, report_json=report()),
        ]
        audit = build_system_audit(records=records)
        self.assertEqual(audit["recommendation_mix"],
                         {"重注": 1, "适度投入": 1, "做空/撤出": 1, "观望或小注": 1})
        self.assertAlmostEqual(audit["recommendation_mix_ratio"]["重注"], 0.25, places=4)

    def test_quality_metrics(self):
        records = [
            rec(report_json=report(scene_result={"scene_recognized": True},
                                   conflict_detected=True, risk_degraded=True)),
            rec(report_json=report(scene_result={"scene_recognized": False})),
        ]
        quality = build_system_audit(records=records)["quality"]
        self.assertAlmostEqual(quality["scene_recognized_rate"], 0.5, places=4)
        self.assertAlmostEqual(quality["conflict_rate"], 0.5, places=4)
        self.assertAlmostEqual(quality["risk_degraded_rate"], 0.5, places=4)

    def test_survival_clamp_is_detected_and_counted(self):
        clamped = 0.9 * SURVIVAL_CLAMP_FACTOR
        records = [
            rec(p=0.9, q=0.1, b=10.0, f_star=clamped, report_json=report(f_star=clamped)),
            rec(p=0.9, q=0.1, b=10.0, f_star=0.89, report_json=report()),
        ]
        quality = build_system_audit(records=records)["quality"]
        self.assertEqual(quality["survival_clamped_count"], 1)
        self.assertAlmostEqual(quality["survival_clamp_rate"], 0.5, places=4)

    def test_persona_conflict_detection(self):
        payload = json.dumps({"persona_results": [
            {"f_star": 0.9, "weight": 0.5},
            {"f_star": 0.1, "weight": 0.5},
        ]}, ensure_ascii=False)
        audit = build_system_audit(records=[rec(report_json=payload)])
        self.assertEqual(audit["quality"]["persona_conflict_count"], 1)

    def test_persona_agreement_is_not_a_conflict(self):
        payload = json.dumps({"persona_results": [
            {"f_star": 0.5, "weight": 0.5},
            {"f_star": 0.6, "weight": 0.5},
        ]}, ensure_ascii=False)
        audit = build_system_audit(records=[rec(report_json=payload)])
        self.assertEqual(audit["quality"]["persona_conflict_count"], 0)

    def test_heterogeneous_records_do_not_break_aggregation(self):
        """历史记录字段不齐（缺 persona_results / conflict_detected）。"""
        legacy = json.dumps({"loop_type": "slow", "risk_level": "低", "f_star": 0.4},
                            ensure_ascii=False)
        audit = build_system_audit(records=[
            rec(report_json=legacy),
            rec(report_json=report(persona_results=[{"f_star": 0.2, "weight": 1.0}])),
        ])
        self.assertEqual(audit["totals"]["decisions"], 2)
        self.assertEqual(audit["quality"]["persona_conflict_count"], 0)


class TestDataQualityAndLimitations(unittest.TestCase):
    def test_scenario_type_variants_are_flagged(self):
        records = [
            rec(scenario_type="优势积累与动态反馈"),
            rec(scenario_type="优势积累与动态反馈场景"),
            rec(scenario_type="高赔率重注场景"),
        ]
        variants = build_system_audit(records=records)["data_quality"]["scenario_type_variants"]
        self.assertEqual(len(variants), 1)
        self.assertEqual(variants[0]["normalized"], "优势积累与动态反馈")
        self.assertEqual(variants[0]["count"], 2)

    def test_no_variants_when_labels_are_consistent(self):
        records = [rec(scenario_type="高赔率重注场景"), rec(scenario_type="高赔率重注场景")]
        self.assertEqual(
            build_system_audit(records=records)["data_quality"]["scenario_type_variants"], [])

    def test_limitations_are_always_reported(self):
        """能力边界必须如实随结果返回，避免下游把决策级准确率当成 Agent 级。"""
        limitations = build_system_audit(records=[])["limitations"]
        self.assertTrue(limitations)
        joined = "".join(limitations)
        self.assertIn("决策级", joined)
        self.assertIn("分身级反馈", joined)

    def test_capability_profile_failure_degrades(self):
        import vector_store
        original = vector_store.get_user_profile
        vector_store.get_user_profile = lambda: (_ for _ in ()).throw(RuntimeError("chroma 挂了"))
        try:
            audit = build_system_audit(records=[])
        finally:
            vector_store.get_user_profile = original
        self.assertEqual(audit["capability_profile"], {})


class TestMonthlyTrend(unittest.TestCase):
    def test_month_key_parsing(self):
        from audit import month_key
        self.assertEqual(month_key("2026-05-30T01:01:47"), "2026-05")
        self.assertIsNone(month_key(""))
        self.assertIsNone(month_key(None))
        self.assertIsNone(month_key("2026"))
        self.assertIsNone(month_key("not-a-date-at-all"))

    def test_trend_is_chronological_and_aggregated(self):
        records = [
            rec(created_at="2026-05-30T01:00:00", f_star=0.9, feedback_type="useful",
                report_json=report()),
            rec(created_at="2026-05-31T01:00:00", f_star=0.1, feedback_type="inaccurate",
                report_json=report()),
            rec(created_at="2026-06-02T01:00:00", f_star=0.7, feedback_type=None,
                report_json=report()),
        ]
        trend = build_system_audit(records=records)["trend_by_month"]
        self.assertEqual([row["month"] for row in trend], ["2026-05", "2026-06"])

        may, june = trend
        self.assertEqual(may["decisions"], 2)
        self.assertEqual(may["with_feedback"], 2)
        self.assertAlmostEqual(may["accuracy"], 0.5, places=4)
        self.assertEqual(may["heavy_bet_count"], 1)
        self.assertAlmostEqual(may["heavy_bet_share"], 0.5, places=4)
        self.assertAlmostEqual(may["avg_f_star"], 0.5, places=4)

        self.assertEqual(june["decisions"], 1)
        self.assertIsNone(june["accuracy"], "该月无反馈样本时准确率必须是 None")
        self.assertAlmostEqual(june["heavy_bet_share"], 1.0, places=4)

    def test_records_without_usable_timestamp_are_excluded_from_trend(self):
        records = [rec(created_at=None, report_json=report()),
                   rec(created_at="2026-05-30T01:00:00", report_json=report())]
        audit = build_system_audit(records=records)
        self.assertEqual(audit["totals"]["decisions"], 2)
        self.assertEqual(len(audit["trend_by_month"]), 1)

    def test_empty_trend_for_empty_dataset(self):
        self.assertEqual(build_system_audit(records=[])["trend_by_month"], [])


if __name__ == "__main__":
    unittest.main()
