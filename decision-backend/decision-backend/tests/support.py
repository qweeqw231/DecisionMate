# -*- coding: utf-8 -*-
"""
测试公共支撑：把数据落点指向临时目录，确保测试绝不触碰真实数据。

必须在导入 storage / vector_store / main 之前 import 本模块 —— 因为
storage.DB_PATH 与 vector_store 的 Chroma 路径都是在导入时从环境变量读取的。
"""
from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

_TMP_DIR = tempfile.mkdtemp(prefix="decisionmate-tests-")

# load_dotenv() 默认不覆盖已存在的环境变量，因此这两行能确保测试使用隔离副本
os.environ["DECISION_DB_PATH"] = os.path.join(_TMP_DIR, "test_decision.db")
os.environ["CHROMA_DB_PATH"] = os.path.join(_TMP_DIR, "test_chroma")
# 避免测试误用真实密钥发起网络请求
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key-not-used")
os.environ.setdefault("SILICONFLOW_API_KEY", "test-key-not-used")

atexit.register(shutil.rmtree, _TMP_DIR, ignore_errors=True)


def tmp_dir() -> str:
    return _TMP_DIR
