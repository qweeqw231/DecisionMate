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
from factor_guard import FACTOR_MAX, FACTOR_MIN, is_factor_key, is_numeric  # noqa: E402

# Phase 3.3 验收报告记载的「当前能力因子状态」，作为还原基线
BASELINE = {
    "考试备战能力": 0.87,
    "行政博弈能力": 0.83,
    "技术速通能力": 0.92,
    "风险偏好": 0.90,
}

BASIS = "P0 修复：因子被归档流程异常写坏，按 Phase 3.3 验收基线还原"


def backup_chroma() -> str | None:
    """
    写入前备份整个 Chroma 目录。

    P2 加固：
    - 原先只复制 chroma.sqlite3，若进程退出时留下 -wal 兄弟文件，备份可能不完整。
      改为整目录复制，并顺带检查是否存在 -wal（说明可能有进程正在写）。
    - 复制后立刻用 sqlite3 打开校验，避免「备份看起来成功、实际不可读」。
    - 备份放到数据目录之外，避免备份本身又被下一次备份复制进去。
    """
    db_path = os.getenv("CHROMA_DB_PATH", os.path.join(BACKEND_DIR, "chroma_db"))
    if not os.path.isdir(db_path):
        print(f"[备份] 未找到 {db_path}，跳过备份")
        return None

    wal = os.path.join(db_path, "chroma.sqlite3-wal")
    if os.path.exists(wal):
        print("[备份] ⚠ 检测到 chroma.sqlite3-wal：可能有后端进程正在运行。"
              "建议先停止服务再执行 --apply。")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = os.path.join(BACKEND_DIR, f"chroma_db.bak-{stamp}")
    shutil.copytree(db_path, dst)
    print(f"[备份] {db_path} → {dst}")

    backup_db = os.path.join(dst, "chroma.sqlite3")
    if os.path.exists(backup_db):
        import sqlite3
        try:
            con = sqlite3.connect(f"file:{backup_db}?mode=ro", uri=True)
            tables = con.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
            con.close()
            if tables == 0:
                print("[备份] ⚠ 备份可打开但没有任何表，请人工确认")
            else:
                print(f"[备份] 校验通过（{tables} 张表），恢复方式：把该目录复制回 {db_path}")
        except Exception as e:  # noqa: BLE001
            print(f"[备份] ✗ 备份无法打开：{e}")
            return None
    return dst


def parse_overrides(pairs, profile: dict, allowed: set) -> dict:
    """
    解析并校验 --set 覆盖项。

    P2 加固：此前不校验名称，`--set user_id=0.5` 或 `--set 随便什么=0.5`
    会直接写进档案，污染出内部字段或凭空的因子。
    """
    overrides = {}
    for raw in pairs or []:
        if "=" not in raw:
            raise SystemExit(f"--set 参数格式应为 名称=数值，收到：{raw}")
        name, _, value = raw.partition("=")
        name = name.strip()
        if not is_factor_key(name):
            raise SystemExit(f"--set 的名称非法（不能是 user_id 或 *_basis / *_updated_at）：{name}")
        if name not in allowed:
            raise SystemExit(
                f"--set 的名称不在可还原范围内：{name}\n"
                f"  当前档案中的因子：{sorted(k for k in profile if is_factor_key(k))}\n"
                f"  还原基线中的因子：{sorted(BASELINE)}"
            )
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

    profile = vector_store.get_user_profile()
    if not profile:
        print("✗ 能力档案为空，无法修复（user_profile 集合中没有 user_default 记录）")
        return 1

    allowed = set(BASELINE) | {k for k in profile if is_factor_key(k)}
    target = dict(BASELINE)
    target.update(parse_overrides(args.set, profile, allowed))

    print("=" * 68)
    print("当前档案 → 计划还原值")
    print("=" * 68)
    problems = []
    for name in sorted(set(list(target.keys()) + [k for k in profile if is_factor_key(k)])):
        old = profile.get(name, "<不存在>")
        new = target.get(name, "<不在还原基线中，保持不变>")
        flag = ""
        if is_numeric(old):
            if isinstance(new, float) and abs(float(old) - new) >= 0.1:
                flag = "  ← 疑似被写坏"
            elif isinstance(new, float):
                flag = "  （与基线接近）"
        elif old != "<不存在>":
            flag = "  ← 类型异常（非数值）"
            problems.append(name)
        else:
            flag = "  ← 档案中不存在，将被新建"
        print(f"  {name:<12} {str(old):<12} → {new}{flag}")

    # P2 加固：原先这个列表算了却从不打印，等于没有提示
    print()
    if problems:
        print(f"⚠ 发现 {len(problems)} 个类型异常的因子：{'、'.join(problems)}")
        print("  这些是历史脏数据（值是字符串而非数值），还原后会写回合法数值。")
    else:
        print("未发现类型异常的因子。")

    print(f"还原依据：{BASIS}")
    print("注意：被覆盖的历史轨迹无法从 Chroma 还原（metadata 只保留最后一次更新）。")

    if not args.apply:
        print("\n[dry-run] 未写入任何数据。确认无误后加 --apply 执行。")
        return 0

    backup = backup_chroma()
    if backup is None:
        print("✗ 备份未成功，出于安全考虑中止写入（可用 --set 或先修好数据目录后重试）")
        return 1

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
    print(f"\n回滚方式：把 {backup} 复制回数据目录后重启后端。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
