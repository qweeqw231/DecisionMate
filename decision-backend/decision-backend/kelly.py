#kelly.py
"""
凯利公式确定性引擎

为什么需要它
------------
架构 5.3.1 要求量化分析 Agent 内置算法（Python 函数模块），但此前 f* 完全由大模型
在 JSON 里直接给出——代码里没有任何凯利运算。

做 L1（执行中校准）时这个问题会放大：L1 要在执行过程中**反复**重算 f*，并展示
「初始预判 → 校准后」的变化轨迹。如果每次 f* 都由模型现给，轨迹既不可复现也无从验证。

因此约定：**大模型只负责从执行进展中估计 p（胜率）与 b（赔率），f* 一律由本模块计算。**
"""
from __future__ import annotations


class KellyInputError(ValueError):
    """胜率或赔率不满足凯利公式的定义域"""


def validate_params(p: float, b: float) -> tuple[float, float]:
    """
    校验并规范化凯利公式的输入。

    p 为胜率，必须落在 [0, 1]；b 为赔率（收益/损失），必须为正数。
    不满足定义域时抛 KellyInputError，而不是返回一个看似合理的数字。
    """
    try:
        p = float(p)
        b = float(b)
    except (TypeError, ValueError) as exc:
        raise KellyInputError(f"胜率与赔率必须是数值（收到 p={p!r}, b={b!r}）") from exc

    if p != p or b != b:  # NaN
        raise KellyInputError("胜率与赔率不能是 NaN")
    if p in (float("inf"), float("-inf")) or b in (float("inf"), float("-inf")):
        raise KellyInputError("胜率与赔率必须是有限数值")
    if not 0.0 <= p <= 1.0:
        raise KellyInputError(f"胜率 p 必须落在 [0, 1]，收到 {p}")
    if b <= 0:
        raise KellyInputError(f"赔率 b 必须为正数，收到 {b}")
    return p, b


def kelly_fraction(p: float, b: float) -> float:
    """
    计算凯利最优下注比例：f* = p - (1 - p) / b

    f* > 0 表示值得投入（越大越该重注）；f* < 0 表示应当做空/撤出。
    本函数不设上下限——是否削减由 Mux 的「生存优先硬约束」负责，
    两件事分开才能各自被验证。
    """
    p, b = validate_params(p, b)
    q = 1.0 - p
    return p - q / b


def kelly_round(p: float, b: float, digits: int = 4) -> float:
    """按指定精度返回 f*（统一四舍五入口径，避免轨迹里出现浮点毛刺）。"""
    return round(kelly_fraction(p, b), digits)
