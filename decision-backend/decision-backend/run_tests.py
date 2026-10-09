# -*- coding: utf-8 -*-
"""
P0 回归测试入口

用法（在 decision-backend/decision-backend 目录下）：
    .venv\\Scripts\\python.exe run_tests.py          # 运行全部测试
    .venv\\Scripts\\python.exe run_tests.py -v       # 详细输出

测试数据全部落在系统临时目录，不会触碰 decision.db / chroma_db。
使用标准库 unittest，无需额外安装 pytest（也可直接被 pytest 收集）。
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)


def main() -> int:
    verbosity = 2 if ("-v" in sys.argv or "--verbose" in sys.argv) else 1
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=os.path.join(HERE, "tests"),
                            top_level_dir=HERE,
                            pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=verbosity).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
