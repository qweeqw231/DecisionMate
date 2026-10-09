# -*- coding: utf-8 -*-
r"""
P0 修复工具：还原被写坏的用户能力画像

背景
----
archive_agent 曾把大模型返回的因子新值原样写入能力档案（无钳制、无范围校验），
每一轮复盘都把因子推向极端，实测被写坏为：

    考试备战能力 0.85 → 0.28
    行政博弈能力 0.80 → 0.07
    技术速通能力 0.88 → 0.11
    风险偏好     "偏激进" → 0.03

修复后（factor_guard 已上线）不会再有新的污染，但已被覆盖的数值无法自动还原：
Chroma 的 metadata 只保留最后一次更新，真实的历史轨迹不可重建。

因此本脚本把因子还原到**文档记载的最后一个可信状态**（Phase 3.3 验收报告
「四、当前能力因子状态」），并显式标注 basis，便于日后追溯。

用法
----
    python tools\repair_profile.py                # 只查看将要写入什么（默认 dry-run）
    python tools\repair_profile.py --apply        # 实际写入（先自动备份 chroma.sqlite3）
    python tools\repair_profile.py --apply --set 技术速通能力=0.9 --set 风险偏好=0.8
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(BACKEND_DIR, ".env"))

import vector_store  # noqa: E402
from factor_guard import FACTOR_MAX, FACTOR_MIN, is_numeric  # noqa: E402

# Phase 3.3 验收报告记载的「当前能力因子状态」，作为还原基线
BASELINE = {
    "考试备战能力": 0.87,
    "行政博弈能力": 0.83,
    "技术速通能力": 0.92,
    "风险偏好": 0.90,
}

BASIS = "P0 修复：因子被归档流程异常写坏，按 Phase 3.3 验收基线还原"


def backup_chroma() -> str | None:
    """写入前备份 Chroma 的 SQLite 文件。"""
    db_path = os.getenv("CHROMA_DB_PATH", os.path.join(BACKEND_DIR, "chroma_db"))
    src = os.path.join(db_path, "chroma.sqlite3")
    if not os.path.exists(src):
        print(f"[备份] 未找到 {src}，跳过备份")
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = os.path.join(os.path.dirname(src), f"chroma.sqlite3.bak-{stamp}")
    shutil.copy2(src, dst)
    print(f"[备份] {src} → {dst}")
    return dst


def parse_overrides(pairs) -> dict:
    overrides = {}
    for raw in pairs or []:
        if "=" not in raw:
            raise SystemExit(f"--set 参数格式应为 名称=数值，收到：{raw}")
        name, _, value = raw.partition("=")
        name = name.strip()
        try:
            num = float(value)
        except ValueError:
            raise SystemExit(f"--set 的数值无法解析：{raw}")
        if not (FACTOR_MIN <= num <= FACTOR_MAX):
            raise SystemExit(f"--set 数值超出 [{FACTOR_MIN}, {FACTOR_MAX}]：{raw}")
        overrides[name] = num
    return overrides


def main() -> int:
    parser = argparse.ArgumentParser(description="还原被写坏的用户能力画像（P0）")
    parser.add_argument("--apply", action="store_true", help="实际写入；缺省为 dry-run")
    parser.add_argument("--set", action="append", metavar="名称=数值",
                        help="覆盖某个因子的还原值，可重复")
    args = parser.parse_args()

    target = dict(BASELINE)
    target.update(parse_overrides(args.set))

    profile = vector_store.get_user_profile()
    if not profile:
        print("✗ 能力档案为空，无法修复（user_profile 集合中没有 user_default 记录）")
        return 1

    print("=" * 68)
    print("当前档案 → 计划还原值")
    print("=" * 68)
    problems = []
    for name in sorted(set(list(target.keys()) + [k for k in profile if not k.endswith(("_updated_at", "_basis")) and k != "user_id"])):
        old = profile.get(name, "<不存在>")
        new = target.get(name, "<不在还原基线中，保持不变>")
        flag = ""
        if is_numeric(old):
            if isinstance(new, float) and abs(float(old) - new) >= 0.1:
                flag = "  ← 疑似被写坏"
        elif old != "<不存在>":
            flag = "  ← 类型异常（非数值）"
            problems.append(name)
        print(f"  {name:<12} {str(old):<12} → {new}{flag}")

    print()
    print(f"还原依据：{BASIS}")
    print("注意：被覆盖的历史轨迹无法从 Chroma 还原（metadata 只保留最后一次更新）。")

    if not args.apply:
        print("\n[dry-run] 未写入任何数据。确认无误后加 --apply 执行。")
        return 0

    backup_chroma()

    now = datetime.now().isoformat()
    updates = {}
    for name, value in target.items():
        updates[name] = value
        updates[f"{name}_updated_at"] = now
        updates[f"{name}_basis"] = BASIS

    vector_store.update_user_profile(updates)

    after = vector_store.get_user_profile()
    print("\n写入完成，当前档案：")
    print(json.dumps({k: v for k, v in sorted(after.items()) if not k.endswith("_basis")},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
