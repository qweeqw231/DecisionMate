#agent_core/json_utils.py
"""
LLM 输出解析工具（P0 修复）

背景：原先各个 Agent 各自实现 JSON 提取与布尔值转换，风格不一：
- quant_agent 会剥离代码块并截取首个 { 到最后一个 }；
- risk_agent / archive_agent 只剥离开头的代码块标记，前面多一句解释就整段解析失败；
- risk_agent 用 bool(data["bankruptcy_risk"]) 转换，字符串 "false" 会被判成 True，
  在安全关键路径上把「无风险」和「有风险」弄反。

本模块提供唯一实现，供所有 Agent 共用，避免再次漂移。
"""
from __future__ import annotations

import json
from typing import Any


class LLMParseError(ValueError):
    """LLM 输出无法解析为预期的 JSON 对象"""


def extract_json_object(text: str | None) -> dict:
    """
    从 LLM 回复中提取第一个 JSON 对象。

    容忍：Markdown 代码块包裹、JSON 前后的解释性文字、首尾空白。
    失败时抛出 LLMParseError（是 ValueError 的子类，便于统一捕获）。
    """
    if text is None:
        raise LLMParseError("响应为 None")
    if not isinstance(text, str):
        raise LLMParseError(f"响应类型异常：{type(text).__name__}")

    body = text.strip()
    if not body:
        raise LLMParseError("响应为空字符串")

    # 剥离 Markdown 代码块（```json ... ``` 或 ``` ... ```）
    if body.startswith("```"):
        first_newline = body.find("\n")
        if first_newline != -1:
            body = body[first_newline + 1:]
        if body.rstrip().endswith("```"):
            body = body.rstrip()[:-3]
        body = body.strip()

    # 截取首个 '{' 到最后一个 '}'，容忍前后多余文字
    start = body.find("{")
    end = body.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise LLMParseError(f"未找到 JSON 对象，原始输出片段：{text[:200]!r}")

    try:
        parsed = json.loads(body[start:end + 1])
    except json.JSONDecodeError as exc:
        raise LLMParseError(f"JSON 解析失败：{exc}；原始输出片段：{text[:200]!r}") from exc

    if not isinstance(parsed, dict):
        raise LLMParseError(f"JSON 顶层不是对象，而是 {type(parsed).__name__}")
    return parsed


_TRUE_TOKENS = {"true", "1", "yes", "y", "是", "有"}
_FALSE_TOKENS = {"false", "0", "no", "n", "否", "无", ""}


def as_bool(value: Any, default: bool) -> bool:
    """
    宽松但方向明确的布尔转换。

    与 bool(value) 的关键区别：字符串 "false" / "0" / "否" 会被识别为 False，
    而不是因为它们非空而被判成 True。

    value 无法识别时返回 default —— 调用方用 default 表达「失败时倒向哪一边」，
    安全关键字段必须传 fail-safe 方向（True）。
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        token = value.strip().lower()
        if token in _TRUE_TOKENS:
            return True
        if token in _FALSE_TOKENS:
            return False
    return default
