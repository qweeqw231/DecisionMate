#agent_core/calibration_agent.py
"""
L1 执行中校准 Agent（架构 6.1 / 6.2）

定位
----
L1 是系统区别于「一次性算命」工具的核心能力：决策在执行过程中，每出现一次
阶段性结果，就重新校准胜率 p 与赔率 b，重算 f*，并判断「继续执行」还是「及时止损」。
架构 6.2 明确要求：初始参数与执行中修正后的参数分别计算 f*，**对比展示变化轨迹**。

职责边界
--------
大模型只负责一件事：根据执行进展，重新估算当前的 p 与 b。
f* 一律交由 kelly.py 确定性计算——否则轨迹不可复现、也无法验证。

失败方向
--------
模型输出不合法（p 越界、b 非正、无法解析）时**不编造新参数**：
沿用上一次已知参数，并把 degraded 置 True。判定照旧由这组旧参数推出，
保持自洽；「本次没有真正重新校准」由 degraded 表达。
理由：执行中的仓位上，一个凭空生成的数字比「这次没算出来」危险得多。
"""
from __future__ import annotations

import logging
from typing import Optional

from agent_core.ai_client import chat
from agent_core.json_utils import extract_json_object
from agent_core.mux import advice_band, advice_headline
from kelly import KellyInputError, kelly_fraction, validate_params
from models.schemas import CalibrationResult

CALIBRATION_SYSTEM_PROMPT = """你是决策执行过程中的「校准分析专家」。用户的某个决策已经在执行，
现在他汇报了一条阶段性结果。你的任务是**重新估算当前的胜率 p 与赔率 b**。

## 你要输出的两个数
- **p**：以现在的信息看，这个决策最终取得预期成功的概率（0~1）。
- **b**：以现在的信息看，继续投入所能获得的收益 / 已投入与待投入的成本（收益损失比，必须 > 0）。

## 判断要点
- 进展**好于**预期 → p 上调；进展**慢于/差于**预期 → p 下调，或赔率被压缩。
- 已经投入的成本属于沉没成本，**只影响 b，不要直接当成「不能放弃」的理由**。
- 如果阶段性结果暴露出原计划的关键假设不成立，p 与 b 都应显著下修。
- 如果已经接近完成且结果符合预期，b 会变小（剩余收益有限），但 p 通常较高。
- 若用户报告的是失败/受阻，不要为了安慰而虚高 p。

## 输出格式
必须严格输出一个 JSON 对象，不要输出其他任何内容：
{
  "p": 0.0,
  "b": 0.0,
  "reasoning": "说明你如何从这条进展推断出新的 p 与 b"
}
"""


def verdict_for_f_star(f_star: float) -> str:
    """
    由校准后的 f* 判定执行建议（阈值与报告文案共用 mux.advice_band，避免口径分裂）：
    f* > 0.2 → continue（继续执行）；0 <= f* <= 0.2 → watch（观望）；f* < 0 → stop（及时止损）。
    """
    band = advice_band(f_star)
    if band in ("重注", "适度投入"):
        return "continue"
    if band == "观望或小注":
        return "watch"
    return "stop"


def _last_known(initial: dict, history: list) -> tuple[float, float, float, float]:
    """取「上一次已知参数」：优先最近一次校准，否则用初始值。"""
    if history:
        last = history[-1]
        return float(last["p"]), float(last["q"]), float(last["b"]), float(last["f_star"])
    return (float(initial["p"]), float(initial["q"]),
            float(initial["b"]), float(initial["f_star"]))


def _degraded_result(initial: dict, history: list, reason: str) -> CalibrationResult:
    """
    校准失败时的兜底：沿用上一次参数，并把判定按这套「旧参数」照常推出来。

    这里刻意不硬编码成「观望」——判定必须与它依据的那组参数自洽，
    否则轨迹上会出现「f*=0.89 却判定观望」这种自相矛盾。
    本次「没有真正重新校准」这件事由 degraded 标记表达。
    """
    p, q, b, _ = _last_known(initial, history)
    f_star = kelly_fraction(p, b)
    return CalibrationResult(
        p=p, q=q, b=b, f_star=round(f_star, 4),
        verdict=verdict_for_f_star(f_star),
        advice=advice_headline(f_star),
        reasoning=f"本次校准未能完成，已沿用上一次的参数（p={p:.2f}, b={b:.2f}）。{reason}",
        degraded=True,
    )


def recalibrate(scenario: str, scenario_type: str, initial: dict,
                history: Optional[list] = None, note: str = "") -> CalibrationResult:
    """
    根据一条阶段性进展重新估算 p、b 并重算 f*。

    参数:
        scenario:      原始决策场景描述
        scenario_type: 原始场景类型
        initial:       初始参数 {p, q, b, f_star}
        history:       既往校准记录（storage.get_execution_updates 的返回）
        note:          本次阶段性进展描述
    """
    history = history or []

    history_text = ""
    if history:
        lines = [
            f"- 第{i}次进展：{item.get('note', '')}（当时重估 p={item.get('p')}, b={item.get('b')}, "
            f"f*={item.get('f_star')}）"
            for i, item in enumerate(history, 1)
        ]
        history_text = "\n## 既往进展\n" + "\n".join(lines) + "\n"

    user_message = f"""## 原始决策
{scenario}

初始场景类型：{scenario_type or '（未识别）'}

## 初始参数（决策时的预判）
- 胜率 p = {initial.get('p')}
- 败率 q = {initial.get('q')}
- 赔率 b = {initial.get('b')}
- 凯利值 f* = {initial.get('f_star')}
{history_text}
## 本次阶段性结果
{note}

请据此重新估算当前的 p 与 b。"""

    try:
        response_text = chat(
            system_prompt=CALIBRATION_SYSTEM_PROMPT,
            user_message=user_message,
            temperature=0.2,
            max_tokens=1024,
        )
        data = extract_json_object(response_text)
        p = float(data["p"])
        b = float(data["b"])
        p, b = validate_params(p, b)
        reasoning = str(data.get("reasoning") or "").strip()
    except (KellyInputError, KeyError, TypeError, ValueError) as e:
        logging.warning("[L1校准] 模型输出不可用，沿用上一次参数：%s", e)
        return _degraded_result(initial, history, f"原因：{e}")
    except Exception as e:  # noqa: BLE001 —— 网络/解析异常同样不得编造数字
        logging.warning("[L1校准] 调用失败，沿用上一次参数：%s", e)
        return _degraded_result(initial, history, f"原因：{e}")

    q = round(1.0 - p, 4)
    f_star = round(kelly_fraction(p, b), 4)
    return CalibrationResult(
        p=round(p, 4), q=q, b=round(b, 4), f_star=f_star,
        verdict=verdict_for_f_star(f_star),
        advice=advice_headline(f_star),
        reasoning=reasoning or "模型未给出推理说明。",
    )
