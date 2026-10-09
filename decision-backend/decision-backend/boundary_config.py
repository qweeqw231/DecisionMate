#boundary_config.py
"""
关系边界配置（P1-4）

架构 5.3.4「关系边界Agent」要求：当识别到用户描述中包含「具体的、平等的他人」时，
主动挂起所有量化分析模块，输出固定提示，且**不记录此场景的详细数据**。

配置项由用户掌握（架构 6.4：L3 反馈由用户亲手调整底层参数，包括伦理边界的触发条件），
因此这里把「开关 / 硬规则 / 关机文案 / 是否落库」全部做成可配置，持久化在
SQLite 的 app_settings 表（值为 JSON），默认值即架构要求的形态。
"""
from __future__ import annotations

import logging
from typing import Any

from storage import get_setting, set_setting, get_setting_updated_at

SETTING_KEY = "boundary_config"

# 架构 5.3.4 规定的固定提示文案
DEFAULT_SHUTDOWN_MESSAGE = (
    "此场景超出系统量化边界。你面对的是一个和你一样拥有独立意志和完整情感的平等个体，"
    "请用你的直觉和真诚去感受，而不是用公式去计算。"
)

# 硬规则默认词表。刻意收窄：只覆盖「决策对象明确是某个具体他人」的表述，
# 更细的边界（自我审视 vs 物化他人）交给语义判定，避免关键词误伤。
DEFAULT_HARD_PATTERNS = [
    "追她", "追他", "该不该追", "要不要追",
    "向她表白", "向他表白", "表白",
    "喜欢她", "喜欢他",
    "挽回她", "挽回他",
]

MAX_PATTERNS = 200
MAX_PATTERN_LENGTH = 40
MAX_MESSAGE_LENGTH = 1000

DEFAULTS: dict[str, Any] = {
    "enabled": True,               # 是否启用关系边界保护
    "use_semantic_check": True,    # 硬规则之外，是否再调用大模型做语义判定
    "hard_patterns": DEFAULT_HARD_PATTERNS,
    "shutdown_message": DEFAULT_SHUTDOWN_MESSAGE,
    "skip_persistence": True,      # 命中边界时不写 messages / decision_records / 向量库
}

# 用户可修改的字段白名单
EDITABLE_FIELDS = ("enabled", "use_semantic_check", "hard_patterns",
                   "shutdown_message", "skip_persistence")


def default_config() -> dict:
    """返回一份独立的默认配置副本（避免调用方改到模块级常量）。"""
    return {
        "enabled": DEFAULTS["enabled"],
        "use_semantic_check": DEFAULTS["use_semantic_check"],
        "hard_patterns": list(DEFAULT_HARD_PATTERNS),
        "shutdown_message": DEFAULT_SHUTDOWN_MESSAGE,
        "skip_persistence": DEFAULTS["skip_persistence"],
    }


def _clean_patterns(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("hard_patterns 必须是字符串列表")
    cleaned: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"hard_patterns 只能包含字符串，收到 {type(item).__name__}")
        token = item.strip()
        if not token:
            continue
        if len(token) > MAX_PATTERN_LENGTH:
            raise ValueError(f"规则「{token[:20]}…」过长（上限 {MAX_PATTERN_LENGTH} 字符）")
        if token not in cleaned:
            cleaned.append(token)
    if len(cleaned) > MAX_PATTERNS:
        raise ValueError(f"规则条数过多（上限 {MAX_PATTERNS} 条）")
    return cleaned


def validate_config(updates: dict) -> dict:
    """
    校验并规范化用户提交的配置片段。

    只接受 EDITABLE_FIELDS 中的字段；类型/取值不合法一律抛 ValueError（接口层转 400）。
    """
    if not isinstance(updates, dict):
        raise ValueError("配置必须是 JSON 对象")

    unknown = [key for key in updates if key not in EDITABLE_FIELDS]
    if unknown:
        raise ValueError(f"不支持的配置项：{', '.join(sorted(unknown))}")

    result: dict[str, Any] = {}
    for key, value in updates.items():
        if key in ("enabled", "use_semantic_check", "skip_persistence"):
            if not isinstance(value, bool):
                raise ValueError(f"{key} 必须是布尔值")
            result[key] = value
        elif key == "hard_patterns":
            result[key] = _clean_patterns(value)
        elif key == "shutdown_message":
            if not isinstance(value, str) or not value.strip():
                raise ValueError("shutdown_message 不能为空")
            if len(value) > MAX_MESSAGE_LENGTH:
                raise ValueError(f"shutdown_message 过长（上限 {MAX_MESSAGE_LENGTH} 字符）")
            result[key] = value.strip()
    return result


def load_config() -> dict:
    """
    读取当前配置；缺失字段用默认值补齐，存储内容损坏时回退到默认值。

    绝不抛异常——边界检查位于每次决策的最前面，配置读取失败不应让系统不可用。
    """
    config = default_config()
    try:
        stored = get_setting(SETTING_KEY, None)
    except Exception as e:  # noqa: BLE001
        logging.warning("[关系边界] 读取配置失败，使用默认值：%s", e)
        return config

    if not isinstance(stored, dict):
        return config

    for key in EDITABLE_FIELDS:
        if key not in stored:
            continue
        try:
            config.update(validate_config({key: stored[key]}))
        except ValueError as e:
            logging.warning("[关系边界] 配置项 %s 不合法，沿用默认值：%s", key, e)
    return config


def save_config(updates: dict) -> dict:
    """校验后合并写入，返回完整配置。"""
    clean = validate_config(updates)
    merged = load_config()
    merged.update(clean)
    set_setting(SETTING_KEY, merged)
    return merged


def reset_config() -> dict:
    """恢复默认配置。"""
    config = default_config()
    set_setting(SETTING_KEY, config)
    return config


def config_metadata() -> dict:
    """供 L3 审计展示：当前配置 + 最近更新时间 + 默认值，便于用户判断是否被改动过。"""
    return {
        "current": load_config(),
        "defaults": default_config(),
        "updated_at": _safe_updated_at(),
    }


def _safe_updated_at():
    try:
        return get_setting_updated_at(SETTING_KEY)
    except Exception:  # noqa: BLE001
        return None
