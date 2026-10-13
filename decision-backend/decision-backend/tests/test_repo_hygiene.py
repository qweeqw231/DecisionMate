# -*- coding: utf-8 -*-
"""
仓库卫生检查的单元测试

背景：这条检查最初是内联 bash + grep -E，把 glob `*.db` 当正则用，
GNU grep 忽略前导 `*` 后等价于 `.db`，于是 FeedbackBar.vue 里的
`Fee`**`db`**`ack` 被判成数据库文件，第一次推送 CI 就红了。
Windows 的 .NET 正则直接拒绝 `*.db`，所以本地根本复现不出来。

这里的用例就是为那类「只在 Linux 上才暴露的正则错误」兜底：
把真实仓库文件列表喂进去，逐一断言不误伤、且真违规会被抓住。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import support  # noqa: F401

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import check_repo_hygiene as hygiene  # noqa: E402


def fake_key(body_len: int = 24) -> str:
    """
    运行时拼出一个「像真实密钥」的字符串。

    刻意不写字面量：否则本测试文件自己就会被扫描器命中，
    变成「扫描器的测试用例被扫描器拦下」的自指死循环。
    拼装写法也让「这是测试数据」在源码里一目了然。
    """
    return "sk-" + ("abcdefghijklmnopqrstuvwxyz012345" * 2)[:body_len]


class TestForbiddenPaths(unittest.TestCase):
    def test_real_violations_are_caught(self):
        cases = [
            "decision-backend/decision-backend/.env",
            ".env",
            "decision-backend/decision-backend/decision.db",
            "test-harness/test_results.db",
            "decision-backend/decision-backend/decision.db-wal",
            "decision-backend/decision-backend/chroma_db/chroma.sqlite3",
            "web-frontend/node_modules/vue/index.js",
            "decision-backend/decision-backend/.venv/Scripts/python.exe",
            "DecisionMate-frontend/oh_modules/@ohos/hypium/index.js",
        ]
        for path in cases:
            with self.subTest(path=path):
                self.assertTrue(hygiene.find_forbidden_paths([path]), f"应被拦下：{path}")

    def test_feedback_bar_is_not_mistaken_for_a_database(self):
        """
        回归：这是当初 CI 变红的直接原因——
        `*.db` 被当成正则后等价于 `.db`，而 FeedbackBar 里含 "db"。
        """
        path = "web-frontend/src/components/report/FeedbackBar.vue"
        self.assertEqual(hygiene.find_forbidden_paths([path]), [])

    def test_other_innocent_paths_are_not_flagged(self):
        """凡是「.db 出现在文件名中间」的路径都不该被误伤。"""
        innocent = [
            "web-frontend/src/components/report/FeedbackBar.vue",
            "docs/db-design.md",
            "scripts/db_migrate.py",
            "web-frontend/src/api/db.ts",
            "decision-backend/decision-backend/db_utils.py",
            "web-frontend/src/components/chat/MessageBubble.vue",
        ]
        self.assertEqual(hygiene.find_forbidden_paths(innocent), [])

    def test_env_example_is_allowed(self):
        self.assertEqual(
            hygiene.find_forbidden_paths(["decision-backend/decision-backend/.env.example"]),
            [])
        # 但真正的 .env 仍然要拦
        self.assertTrue(hygiene.find_forbidden_paths(["decision-backend/decision-backend/.env"]))

    def test_patterns_are_anchored_to_the_extension(self):
        """.db 必须是扩展名结尾，不能匹配 .dbt / .dbml 之类。"""
        self.assertEqual(
            hygiene.find_forbidden_paths(["db/schema.dbml", "assets/sample.dbt"]), [])

    def test_reports_the_matching_rule(self):
        hits = hygiene.find_forbidden_paths(["decision.db"])
        self.assertEqual(len(hits), 1)
        label, path = hits[0]
        self.assertIn("数据库", label)
        self.assertEqual(path, "decision.db")

    def test_backslashes_are_normalized(self):
        """Windows 路径也应被正确识别。"""
        self.assertTrue(hygiene.find_forbidden_paths([r"web-frontend\node_modules\vue\index.js"]))


class TestSecretScan(unittest.TestCase):
    def test_realistic_key_is_flagged(self):
        files = [("a.py", f'api_key = "{fake_key()}"')]
        self.assertEqual(len(hygiene.find_suspected_secrets(files)), 1)

    def test_placeholders_are_not_flagged(self):
        cases = [
            'DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
            '"DEEPSEEK_API_KEY=sk-<你的密钥>"',
            'api_key="sk-yourownkeyhere000000000000"',
            '# sk-0000000000000000000000000000 (示例占位)',
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assertEqual(
                    hygiene.find_suspected_secrets([("doc.md", text)]), [],
                    f"占位符不该被判成密钥：{text}")

    def test_reports_line_numbers(self):
        files = [("a.py", f"line one\nline two\nkey = '{fake_key()}'\n")]
        hits = hygiene.find_suspected_secrets(files)
        self.assertEqual(hits[0][1], 3)

    def test_short_or_unrelated_strings_are_ignored(self):
        files = [("a.py", "sk-short\n任务完成\n")]
        self.assertEqual(hygiene.find_suspected_secrets(files), [])


class TestAgainstTheRealRepository(unittest.TestCase):
    """把**真实**的已跟踪文件列表喂进去，确保当前仓库是干净的、且不误伤。"""

    def test_actual_repository_passes(self):
        tracked = hygiene._tracked_files()
        self.assertGreater(len(tracked), 0, "应当能读到已跟踪文件列表")
        self.assertEqual(hygiene.find_forbidden_paths(tracked), [],
                         "仓库里存在不该入库的文件")

    def test_actual_repository_has_no_suspected_secrets(self):
        tracked = hygiene._tracked_files()
        self.assertEqual(hygiene.find_suspected_secrets(hygiene._read_text_files(tracked)), [])

    def test_checker_script_itself_is_tracked(self):
        """检查脚本必须入库，否则 CI 跑不到它。"""
        self.assertIn("scripts/check_repo_hygiene.py", hygiene._tracked_files())


if __name__ == "__main__":
    unittest.main()
