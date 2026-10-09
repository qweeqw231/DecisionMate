# -*- coding: utf-8 -*-
"""元认知调度器测试：锁定文档验收表中已通过的用例，防止回归"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import support  # noqa: F401

from main import is_fast_loop  # noqa: E402

# (场景, 期望回路, 来源)
DOCUMENTED_CASES = [
    ("有人插队我要不要当场制止", "fast", "Phase 1 验收表"),
    ("今天中午吃什么", "fast", "Phase 1 验收表"),
    ("我在想要不要花整个周末做深度复盘，因为密卷暴露了设计模式和UML类图的漏洞，但下周还有飞控考试", "slow", "Phase 1/3.2 验收表"),
    ("我在想要不要漫无目的地再刷一天题，虽然下周就考试了但不知道看什么", "slow", "Phase 1 验收表"),
    ("我5月23日软考，5月24日飞控，中间怎么安排？", "slow", "Phase 2/3.2 验收表"),
    ("我5月16日教资面试，5月23日软考", "slow", "Phase 3.2 验收表"),
]


class TestDocumentedRouting(unittest.TestCase):
    def test_documented_acceptance_cases(self):
        for scenario, expected, source in DOCUMENTED_CASES:
            with self.subTest(scenario=scenario):
                actual = "fast" if is_fast_loop(scenario) else "slow"
                self.assertEqual(actual, expected, msg=f"{source}: {scenario}")

    def test_defaults_to_slow_for_unknown_input(self):
        self.assertFalse(is_fast_loop("随便写点什么没有关键字的描述内容"))

    def test_complex_keywords_always_force_slow(self):
        for scenario in ["要不要花三天攻克软考论文", "怎么分配精力", "值不值得", "考研还是工作"]:
            with self.subTest(scenario=scenario):
                self.assertFalse(is_fast_loop(scenario))


if __name__ == "__main__":
    unittest.main()
