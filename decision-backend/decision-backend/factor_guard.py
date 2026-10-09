#factor_guard.py
"""
能力因子写入守卫（P0 修复）

背景（实测事故）
----------------
archive_agent 曾把大模型返回的 factor_updates[因子]["new"] 原样写入能力档案：

    update_user_profile({factor_name: update_info["new"], ...})

ARCHIVE_SYSTEM_PROMPT 要求「调整幅度控制在 ±0.05 以内」，但代码没有任何钳制、
范围校验或类型校验。结果是每一轮复盘都把因子推向极端，实测被写坏为：

    考试备战能力 0.85 → 0.28
    技术速通能力 0.88 → 0.11
    行政博弈能力 0.80 → 0.07
    风险偏好     "偏激进" → 0.03（字符串还被写成了 float）

而这些因子又会被注入量化 Agent 的 Prompt（main.py 的「用户画像」区块），
形成「越用越偏」的自我污染。

本模块为所有能力因子写入提供唯一入口的校验与钳制规则
----------------
1. 只允许更新档案中**已存在**的因子名。新增因子必须由用户在复盘摘要卡片中
   确认后走 POST /api/user-profile/add-factor（Phase 3.3 明确要求系统不得自动写入）。
2. 值必须是有限数值，bool 不算数值（True 会被误当成 1.0）。
3. 值被钳制到 [FACTOR_MIN, FACTOR_MAX]。
4. 单次更新相对当前值的幅度不超过 MAX_STEP，与 Prompt 中的约束保持一致。
5. 当前值不是数值（历史脏数据，如 "偏激进"）时跳过步长限制，允许一次性写入
   合法数值以完成修复，但仍受取值范围约束。
"""
from __future__ import annotations

import math
from typing import Any

# 与 ARCHIVE_SYSTEM_PROMPT 中「调整幅度控制在 ±0.05 以内」保持一致
MAX_STEP = 0.05
FACTOR_MIN = 0.0
FACTOR_MAX = 1.0

# metadata 中与因子值同级的辅助字段，不参与「因子」识别
_META_SUFFIXES = ("_updated_at", "_basis")
_META_KEYS = {"user_id"}


def is_factor_key(key: Any) -> bool:
    """判断 metadata 中的某个键是否代表一个能力因子（而非辅助字段）。"""
    if not isinstance(key, str) or not key:
        return False
    if key in _META_KEYS or key.endswith(_META_SUFFIXES):
        return False
    return True


def is_numeric(value: Any) -> bool:
    """有限数值判定。bool 显式排除（isinstance(True, int) 为真，但其语义不是数值）。"""
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def sanitize_factor_updates(
    current_profile: dict,
    proposed: dict,
) -> tuple[dict, list[str]]:
    """
    校验大模型提出的因子更新。

    参数:
        current_profile: 当前能力档案（含 _updated_at / _basis 等辅助字段）
        proposed:        {因子名: 建议新值}

    返回:
        (accepted, rejections)
        accepted   —— {因子名: 已钳制的安全新值}，只有这些值允许写入
        rejections —— 人类可读的拒绝原因列表，用于日志与复盘上报
    """
    accepted: dict = {}
    rejections: list[str] = []

    if not isinstance(proposed, dict):
        return {}, [f"factor_updates 不是对象（{type(proposed).__name__}），已忽略"]

    for raw_name, raw_value in proposed.items():
        name = raw_name.strip() if isinstance(raw_name, str) else raw_name

        if not is_factor_key(name):
            rejections.append(f"忽略非法因子名：{raw_name!r}")
            continue

        if name not in current_profile:
            rejections.append(
                f"拒绝写入未知因子「{name}」：新增因子需用户确认后经 add-factor 接口写入"
            )
            continue

        if not is_numeric(raw_value):
            rejections.append(
                f"拒绝「{name}」={raw_value!r}：不是有限数值（类型 {type(raw_value).__name__}）"
            )
            continue

        value = float(raw_value)
        bounded = clamp(value, FACTOR_MIN, FACTOR_MAX)
        notes = []
        if bounded != value:
            notes.append(f"越界 {value} → {bounded}")

        current = current_profile.get(name)
        if is_numeric(current):
            low = float(current) - MAX_STEP
            high = float(current) + MAX_STEP
            stepped = clamp(bounded, low, high)
            if stepped != bounded:
                notes.append(f"超出单次步长 ±{MAX_STEP}：{bounded} → {stepped:.4f}")
            bounded = stepped
        else:
            notes.append(f"当前值非数值（{current!r}），按修复处理并跳过步长限制")

        accepted[name] = round(bounded, 4)
        if notes:
            rejections.append(f"「{name}」已钳制：" + "；".join(notes))

    return accepted, rejections


def validate_new_factor(factor_name: Any, value: Any) -> tuple[str, float]:
    """
    校验用户确认新增的因子（POST /api/user-profile/add-factor）。

    新增因子由用户本人确认，因此不施加 ±MAX_STEP 步长限制，
    但仍要求名称合法、值为有限数值且在取值范围内。

    返回 (规范化名称, 钳制后的值)，校验失败抛出 ValueError。
    """
    if not isinstance(factor_name, str) or not factor_name.strip():
        raise ValueError("因子名称不能为空")
    name = factor_name.strip()

    if name in _META_KEYS or name.endswith(_META_SUFFIXES):
        raise ValueError(f"因子名称「{name}」与内部字段冲突，请换一个名称")
    if len(name) > 32:
        raise ValueError("因子名称过长（上限 32 字符）")

    if not is_numeric(value):
        raise ValueError(f"因子值必须是有限数值，收到 {value!r}")

    return name, round(clamp(float(value), FACTOR_MIN, FACTOR_MAX), 4)
