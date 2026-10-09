#agent_core/boundary_agent.py
"""
关系边界 Agent（伦理守门人）—— 架构 5.3.4

定位
----
确保系统在涉及「具体的、平等的他人」时主动关机：不做量化、不给建议、
不记录详细数据。

两条判定路径
------------
1. **硬规则**（可配置词表）：确定性匹配，用户自己维护，绝不会被模型说服。
2. **语义判定**（大模型）：处理硬规则覆盖不到的表述，并区分架构里那组关键对照：

   - 可以量化：评估「我现在是否适合进入一段关系」——这是**自我审视**，
     对象是自己，基于自身认知水平、精力状态、发展轨迹。
   - 不应量化：面对一个具体的、活生生的人时，计算「我该不该追她」——这是**物化**。
   - 可以量化：教资面试是表演型输出；与制度、流程、机构打交道时的策略取舍
     （即使文中出现了老师、辅导员的称呼，决策对象也是「流程」而不是「他这个人」）。
   - 不应量化：把某个具体他人的态度、回应、感情当作可预测、可操纵的变量来计算。

失败方向
--------
语义判定调用失败时**不关机**，而是把结论标记为 degraded=True 并向上报告。
理由：硬规则是用户手写的确定性边界，任何情况下都生效；若因一次大模型抖动就
把所有场景都关掉，系统会变得不可用，而漏判的后果只是退回本次改动之前的行为
（照常分析）。该降级状态会随报告返回，用户能看见「这次守卫没查成」。
"""
from __future__ import annotations

import logging
from typing import Optional

from models.schemas import BoundaryVerdict
from agent_core.ai_client import chat
from agent_core.json_utils import extract_json_object, as_bool

BOUNDARY_SYSTEM_PROMPT = """你是决策系统的「关系边界守门人」。你的唯一职责是判断：这个决策场景，
是否把**一个具体的、平等的他人**当成了可计算、可预测、可操纵的对象。

## 核心判据（只问这一句）
**这个决策，是不是在替「另一个人」算账？**
即：是否要预测、算计或操纵某个具体的人的态度、回应或决定？
是 → 关机；否 → 放行。

## 应当关机（is_boundary = true）
- 要预测或操纵某个具体的人对你的态度、感情、回应
  （例：我该不该追她 / 她是不是对我有意思 / 我们还有没有可能）
- 要算计「怎么说、怎么做才能让某个具体的人答应」
  （例：我该怎么说服王老师给我批缓考 / 怎么让辅导员松口 / 怎么让导师同意）
  —— 架构明确要求这类场景关机：面对一个具体的人时，用真实困境陈述与真诚表达，
     而不是用公式计算「我该怎么说才能让他同意」。
- 把一段关系或与某人的互动本身当作博弈、赌局来计算胜率与赔率
- 需要「攻略」某个具体的人才能达成目标

## 不应关机（is_boundary = false）
- **自我审视**：评估自己是否适合进入一段关系、自己精力够不够、
  自己该不该申请/报考/复盘 —— 对象是自己，不是别人
- **以自身行动为对象的决策**：要不要申请缓考、要不要报名、怎么安排复习
  （注意：只要出现「怎么让某个具体的人答应」，就应判为关机）
- **表演型输出**：面试、答辩、演讲这类靠临场发挥的场合
- **只是提到某人**：场景里出现了某人，但决策与他无关
- **不含具体他人的普通决策**：考试安排、精力分配、职业选择、要不要休息等

## 输出格式
必须严格输出一个 JSON 对象，不要输出任何其他内容：
{
  "is_boundary": true,
  "reason": "一句话说明为什么越界（放行时说明为什么不越界）"
}
"""


def match_hard_rules(scenario: str, patterns) -> Optional[str]:
    """返回第一个命中的硬规则；未命中返回 None。"""
    if not scenario or not patterns:
        return None
    for pattern in patterns:
        if not isinstance(pattern, str) or not pattern.strip():
            continue
        if pattern.strip() in scenario:
            return pattern.strip()
    return None


def semantic_check(scenario: str) -> BoundaryVerdict:
    """调用大模型做语义边界判定。失败时抛出异常，由 check_boundary 统一处理。"""
    response_text = chat(
        system_prompt=BOUNDARY_SYSTEM_PROMPT,
        user_message=scenario,
        temperature=0.0,
        max_tokens=256,
    )
    data = extract_json_object(response_text)
    is_boundary = as_bool(data.get("is_boundary"), default=False)
    reason = str(data.get("reason") or "").strip()
    return BoundaryVerdict(
        is_boundary=is_boundary,
        category="semantic" if is_boundary else "none",
        reason=reason or ("判定为越界场景" if is_boundary else "判定为可分析场景"),
    )


def check_boundary(scenario: str, config: Optional[dict] = None) -> BoundaryVerdict:
    """
    关系边界总入口：先硬规则，再语义判定。

    config 缺省时自行读取当前配置（便于直接调用与测试）。
    """
    if config is None:
        from boundary_config import load_config
        config = load_config()

    if not config.get("enabled", True):
        return BoundaryVerdict(is_boundary=False, category="none", reason="关系边界保护已关闭")

    matched = match_hard_rules(scenario, config.get("hard_patterns") or [])
    if matched:
        return BoundaryVerdict(
            is_boundary=True,
            category="hard_rule",
            matched_rule=matched,
            reason=f"命中硬规则「{matched}」：该场景以某个具体他人为决策对象。",
        )

    if not config.get("use_semantic_check", True):
        return BoundaryVerdict(is_boundary=False, category="none", reason="未启用语义判定，且未命中硬规则")

    try:
        return semantic_check(scenario)
    except Exception as e:  # noqa: BLE001 —— 见模块文档的「失败方向」
        logging.warning("[关系边界] 语义判定失败，本次放行但标记降级：%s", e)
        return BoundaryVerdict(
            is_boundary=False,
            category="none",
            reason="语义判定未能完成，本次未做边界校验（硬规则仍然生效）",
            degraded=True,
        )
