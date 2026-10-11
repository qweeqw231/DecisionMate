# -*- coding: utf-8 -*-
"""复盘归档 Agent 测试（P0-1：因子写入必须经过守卫）"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import support  # noqa: F401

from agent_core import archive_agent  # noqa: E402

PROFILE = {
    "user_id": "default",
    "考试备战能力": 0.85,
    "考试备战能力_updated_at": "2026-05-29",
    "考试备战能力_basis": "软考战损修复验证",
    "技术速通能力": 0.88,
    "风险偏好": 0.85,
}


class ArchiveHarness:
    """把 LLM 调用与档案读写都替换掉，只验证归档 Agent 自身的决策逻辑。"""

    def __init__(self, llm_output, profile=None):
        self.llm_output = llm_output
        self.profile = dict(profile or PROFILE)
        self.writes = []

    def __enter__(self):
        self._orig = (archive_agent.chat, archive_agent.get_user_profile,
                      archive_agent.update_user_profile)

        archive_agent.chat = lambda **kwargs: self.llm_output
        archive_agent.get_user_profile = lambda: dict(self.profile)

        def fake_update(updates):
            self.writes.append(dict(updates))
            self.profile.update(updates)

        archive_agent.update_user_profile = fake_update
        return self

    def __exit__(self, *exc):
        (archive_agent.chat, archive_agent.get_user_profile,
         archive_agent.update_user_profile) = self._orig
        return False

    def run(self):
        return archive_agent.run_archive(
            decision_id=1, initial_f_star=0.89, p=0.9, q=0.1, b=10.0,
            scenario_type="高赔率重注场景", feedback_type="useful",
            feedback_text="实际完成了",
        )


def payload(factor_updates, proposal=None, deviation="偏差分析"):
    return json.dumps({
        "deviation_analysis": deviation,
        "factor_updates": factor_updates,
        "reusable_pattern": "深度复盘类决策胜率常高于预估",
        "new_factor_proposal": proposal,
    }, ensure_ascii=False)


class TestGuardIntegration(unittest.TestCase):
    def test_catastrophic_value_is_clamped_before_write(self):
        """事故原形：模型直接给出 0.28，写库的值必须被限制在 0.85±0.05。"""
        raw = {"考试备战能力": {"old": 0.85, "new": 0.28, "reason": "下调"}}
        with ArchiveHarness(payload(raw)) as h:
            report = h.run()
        written = h.profile["考试备战能力"]
        self.assertAlmostEqual(written, 0.80, places=4)
        self.assertAlmostEqual(report.factor_updates["考试备战能力"]["new"], 0.80, places=4)
        self.assertAlmostEqual(report.factor_updates["考试备战能力"]["old"], 0.85, places=4)

    def test_unknown_factor_is_not_written(self):
        raw = {"抗压能力": {"old": 0.5, "new": 0.8, "reason": "新发现"}}
        with ArchiveHarness(payload(raw)) as h:
            report = h.run()
        self.assertNotIn("抗压能力", h.profile)
        self.assertNotIn("抗压能力", report.factor_updates)
        self.assertTrue(any("未知因子" in r for r in report.guard_rejections))
        self.assertEqual(h.writes, [])

    def test_non_numeric_value_is_not_written(self):
        raw = {"考试备战能力": {"old": 0.85, "new": "很高", "reason": "x"}}
        with ArchiveHarness(payload(raw)) as h:
            report = h.run()
        self.assertAlmostEqual(h.profile["考试备战能力"], 0.85, places=4)
        self.assertEqual(report.factor_updates, {})
        self.assertTrue(report.guard_rejections)

    def test_legitimate_small_change_is_applied(self):
        raw = {"考试备战能力": {"old": 0.85, "new": 0.87, "reason": "表现优于预估"}}
        with ArchiveHarness(payload(raw)) as h:
            report = h.run()
        self.assertAlmostEqual(h.profile["考试备战能力"], 0.87, places=4)
        self.assertAlmostEqual(report.factor_updates["考试备战能力"]["new"], 0.87, places=4)
        self.assertEqual(report.guard_rejections, [])
        # basis 与时间戳必须一并写入，保持档案自洽
        self.assertEqual(h.profile["考试备战能力_basis"], "表现优于预估")
        self.assertIn("考试备战能力_updated_at", h.profile)

    def test_meta_keys_are_ignored(self):
        raw = {"考试备战能力_basis": {"new": "篡改"}, "考试备战能力": {"new": 0.86}}
        with ArchiveHarness(payload(raw)) as h:
            report = h.run()
        self.assertEqual(list(report.factor_updates.keys()), ["考试备战能力"])
        self.assertNotEqual(h.profile["考试备战能力_basis"], "篡改")

    def test_string_current_value_is_repaired_in_place(self):
        profile = dict(PROFILE, 风险偏好="偏激进")
        raw = {"风险偏好": {"old": "偏激进", "new": 0.9, "reason": "类型修复"}}
        with ArchiveHarness(payload(raw), profile=profile) as h:
            h.run()
        self.assertAlmostEqual(h.profile["风险偏好"], 0.9, places=4)


class TestNewFactorProposal(unittest.TestCase):
    def test_proposal_is_parsed(self):
        proposal = {"factor_name": "抗压能力", "suggested_value": 0.8, "basis": "连续3次",
                    "supporting_decisions": [1, 2, 3], "data_insufficient": False}
        with ArchiveHarness(payload({}, proposal=proposal)) as h:
            report = h.run()
        self.assertIsNotNone(report.new_factor_proposal)
        self.assertEqual(report.new_factor_proposal.factor_name, "抗压能力")
        # 提议不得被自动写入档案（Phase 3.3：必须用户确认）
        self.assertNotIn("抗压能力", h.profile)
        self.assertEqual(h.writes, [])


class TestFailureHandling(unittest.TestCase):
    def test_unparseable_output_does_not_raise(self):
        with ArchiveHarness("抱歉，我无法分析。") as h:
            report = h.run()
        self.assertEqual(report.factor_updates, {})
        self.assertTrue(report.guard_rejections)
        self.assertEqual(h.writes, [])

    def test_missing_factor_updates_key_is_tolerated(self):
        with ArchiveHarness('{"deviation_analysis": "只有偏差分析"}') as h:
            report = h.run()
        self.assertEqual(report.factor_updates, {})
        self.assertEqual(h.writes, [])


class TestPartialWriteReporting(unittest.TestCase):
    """
    P2 修复：逐个因子写入并各自兜错。

    原实现把全部写入放在同一个 try 里，写到一半失败会整体跳到 except，
    于是已经写进去的因子被上报成 factor_updates={} —— 报告少报了实际发生的事。
    """

    def test_partial_failure_still_reports_what_was_written(self):
        raw = {
            "考试备战能力": {"old": 0.85, "new": 0.87, "reason": "先写这个"},
            "技术速通能力": {"old": 0.88, "new": 0.90, "reason": "这个会失败"},
        }
        original = archive_agent.update_user_profile
        written = []

        def flaky(updates):
            name = next(iter(updates))
            if name == "技术速通能力":
                raise RuntimeError("向量库写入失败")
            written.append(name)
            h.profile.update(updates)

        with ArchiveHarness(payload(raw)) as h:
            archive_agent.update_user_profile = flaky
            try:
                report = h.run()
            finally:
                archive_agent.update_user_profile = original

        # 成功的那个必须如实上报
        self.assertIn("考试备战能力", report.factor_updates)
        self.assertAlmostEqual(report.factor_updates["考试备战能力"]["new"], 0.87, places=4)
        # 失败的不得谎报为已写入
        self.assertNotIn("技术速通能力", report.factor_updates)
        # 失败原因要出现在守卫记录里
        self.assertTrue(any("写入失败" in r for r in report.guard_rejections))
        # 复盘本身不能被中断
        self.assertNotIn("复盘分析异常", report.deviation_analysis)

    def test_total_write_failure_still_returns_a_report(self):
        original = archive_agent.update_user_profile

        def always_fail(updates):
            raise RuntimeError("向量库整体不可用")

        raw = {"考试备战能力": {"old": 0.85, "new": 0.87, "reason": "x"}}
        with ArchiveHarness(payload(raw)) as h:
            archive_agent.update_user_profile = always_fail
            try:
                report = h.run()
            finally:
                archive_agent.update_user_profile = original
        self.assertEqual(report.factor_updates, {})
        self.assertTrue(report.guard_rejections)


if __name__ == "__main__":
    unittest.main()
