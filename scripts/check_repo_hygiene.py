# -*- coding: utf-8 -*-
r"""
仓库卫生检查（CI 与本地通用）

为什么是 Python 而不是一段内联 bash
------------------------------------
这条检查最初写在内联 shell 里，用 `grep -E` 去匹配**文件路径**，却把 glob
当成了正则：

    for pattern in '.env' '*.db' ...; do
      git ls-files | grep -E "$pattern"

`*.db` 的前导 `*` 在 ERE 里是「零个或多个空」，GNU grep 会警告
`* at start of expression` 后把它忽略，于是正则退化成 `.db`（任意字符 + "db"），
把 `web-frontend/src/components/report/FeedbackBar.vue` 里的
`Fee`**`db`**`ack` 判成了数据库文件——第一次推送到 GitHub 就红了。
（Windows 上的 .NET 正则直接拒绝 `*.db`，所以本地用 PowerShell 复现不出来，
必须用同一套引擎测。）

因此改为 Python 实现：正则只写一次，且可以用普通单元测试覆盖，
见 tests/test_repo_hygiene.py。

用法：
    python scripts/check_repo_hygiene.py        # 在仓库任意位置执行
退出码 0 = 通过，1 = 发现问题。
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import Iterable, Sequence

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 不允许进入版本库的路径（正则只写一次，且都能被单元测试覆盖）
FORBIDDEN_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("密钥文件", re.compile(r"(^|/)\.env$")),
    ("SQLite 数据库", re.compile(r"\.db$")),
    ("SQLite 数据库临时文件", re.compile(r"\.db-")),
    ("Chroma 向量库", re.compile(r"chroma\.sqlite3$")),
    ("前端依赖", re.compile(r"(^|/)node_modules/")),
    ("Python 虚拟环境", re.compile(r"(^|/)\.venv/")),
    ("鸿蒙依赖", re.compile(r"(^|/)oh_modules/")),
]

# 显式允许的例外（例如 .env.example 是配置样例，必须入库）
ALLOWED_PATHS = re.compile(r"\.env\.example$")

# 疑似真实密钥：sk- 后跟 20 位以上字母数字
SECRET_PATTERN = re.compile(r"sk-[A-Za-z0-9]{20,}")
# 明显的占位符（报错提示里的示例串不该被判成密钥）
PLACEHOLDER_PATTERN = re.compile(
    r"x{8,}|X{8,}|0{8,}|your|YOUR|placeholder|example|示例|你的|<", re.IGNORECASE
)

MAX_SCAN_BYTES = 2 * 1024 * 1024  # 超过 2MB 的文件不做文本扫描


def find_forbidden_paths(paths: Iterable[str]) -> list[tuple[str, str]]:
    """
    返回 [(规则说明, 路径)]，空列表表示通过。

    纯函数，便于用合成路径列表做单元测试。
    """
    violations: list[tuple[str, str]] = []
    for path in paths:
        normalized = path.replace("\\", "/")
        if ALLOWED_PATHS.search(normalized):
            continue
        for label, pattern in FORBIDDEN_PATTERNS:
            if pattern.search(normalized):
                violations.append((label, path))
                break
    return violations


def find_suspected_secrets(files: Sequence[tuple[str, str]]) -> list[tuple[str, int, str]]:
    """
    返回 [(路径, 行号, 该行内容)]，空列表表示通过。

    files 为 (路径, 文本内容) 序列，便于单元测试直接构造。
    """
    hits: list[tuple[str, int, str]] = []
    for path, text in files:
        for lineno, line in enumerate(text.splitlines(), 1):
            if SECRET_PATTERN.search(line) and not PLACEHOLDER_PATTERN.search(line):
                hits.append((path, lineno, line.strip()[:120]))
    return hits


def _tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=REPO_ROOT,
                         capture_output=True, text=True, check=True)
    return [line for line in out.stdout.splitlines() if line.strip()]


def _read_text_files(paths: Iterable[str]) -> list[tuple[str, str]]:
    files: list[tuple[str, str]] = []
    for rel in paths:
        full = os.path.join(REPO_ROOT, rel)
        try:
            if os.path.getsize(full) > MAX_SCAN_BYTES:
                continue
            with open(full, encoding="utf-8") as f:
                files.append((rel, f.read()))
        except (OSError, UnicodeDecodeError):
            # 二进制文件或读不了的文件直接跳过：密钥不可能藏在二进制里
            continue
    return files


def main() -> int:
    tracked = _tracked_files()
    print(f"扫描 {len(tracked)} 个已跟踪文件…")

    problems = 0

    path_violations = find_forbidden_paths(tracked)
    if path_violations:
        print("\n✗ 以下被忽略的内容进了版本库：")
        for label, path in path_violations:
            print(f"    [{label}] {path}")
        problems += len(path_violations)
    else:
        print("✓ 没有密钥 / 数据库 / 依赖目录进入版本库")

    secret_hits = find_suspected_secrets(_read_text_files(tracked))
    if secret_hits:
        print("\n✗ 疑似真实密钥出现在代码里：")
        for path, lineno, snippet in secret_hits:
            print(f"    {path}:{lineno}: {snippet}")
        problems += len(secret_hits)
    else:
        print("✓ 没有发现疑似真实密钥")

    if problems:
        print(f"\n仓库卫生检查未通过（{problems} 项）")
        return 1
    print("\n仓库卫生检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
