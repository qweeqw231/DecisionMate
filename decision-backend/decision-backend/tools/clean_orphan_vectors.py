# -*- coding: utf-8 -*-
"""
P0 修复工具：巡检并清理孤儿决策向量

背景
----
删除对话/清空数据原先只清 SQLite，ChromaDB 中的向量会残留成孤儿，却仍会被
search_similar_decisions 检索出来，当作「历史参考」注入量化 Agent 的 Prompt。
实测向量库中存在两条测试脚本留下的孤儿（id 999 / 1000，test_vector.py 与
test_vector_similar_detect.py 写入）。

主程序现已改为删除时同步清理（storage.get_decision_ids_for_conversation +
vector_store.delete_decision_vectors），本脚本用于清掉历史遗留的孤儿，
以及日后巡检。

用法
----
    python tools\clean_orphan_vectors.py            # 只巡检（默认）
    python tools\clean_orphan_vectors.py --apply    # 实际删除
"""
from __future__ import annotations

import argparse
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(BACKEND_DIR, ".env"))

import storage  # noqa: E402
import vector_store  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="清理孤儿决策向量（P0）")
    parser.add_argument("--apply", action="store_true", help="实际删除；缺省只巡检")
    args = parser.parse_args()

    valid_ids = {str(i) for i in storage.get_all_decision_ids()}
    vector_ids = vector_store.get_all_decision_vector_ids()
    orphans = [vid for vid in vector_ids if vid not in valid_ids]

    print("=" * 68)
    print(f"SQLite 决策记录：{len(valid_ids)} 条")
    print(f"向量库决策向量：{len(vector_ids)} 条")
    print(f"孤儿向量（无对应决策记录）：{len(orphans)} 条")
    print("=" * 68)

    if orphans:
        print("孤儿向量 ID：" + ", ".join(sorted(orphans)[:50])
              + (" ..." if len(orphans) > 50 else ""))

    missing = valid_ids - set(vector_ids)
    if missing:
        print(f"\n另有 {len(missing)} 条决策记录没有向量（属正常：向量入库为后台异步，"
              f"失败或未启用时不会补写）")

    if not orphans:
        print("\n✓ 无需清理")
        return 0

    if not args.apply:
        print("\n[dry-run] 未删除任何向量。确认后加 --apply 执行。")
        return 0

    removed = vector_store.delete_decision_vectors(orphans)
    remaining = [vid for vid in vector_store.get_all_decision_vector_ids() if vid not in valid_ids]
    print(f"\n已删除 {removed} 条向量；复查剩余孤儿：{len(remaining)} 条")
    return 0 if not remaining else 1


if __name__ == "__main__":
    raise SystemExit(main())
