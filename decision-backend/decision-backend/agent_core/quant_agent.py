#agent_core/quant_agent.py
"""
量化分析Agent（DeepSeek版）
职责：基于语义理解，从用户描述中动态提取参数，套用凯利公式计算最优下注比例。

与规则引擎版的关键区别：
- 不再依赖关键词匹配
- AI根据语境动态估算 p、q、b
- 能理解复杂场景中的隐含信息
"""

import json
import re
from models.schemas import QuantResult
from agent_core.ai_client import chat
from typing import Optional

QUANT_SYSTEM_PROMPT = """你是一个量化决策分析专家。你的任务是根据用户描述的决策场景，运用凯利公式进行分析。

## 你的知识库（来自《个人决策支持系统：理论与实战全鉴》）

### 凯利公式
f* = p - q/b
其中 p=胜率, q=败率(q=1-p), b=赔率(收益/损失)

### 三种核心场景

**场景一：高赔率重注（b ≥ 5）**
适用：收益远大于损失。如关键技能速通、核心漏洞修复、深度复盘。
公式退化为 f* ≈ p - q，应果断下重注。
历史锚点：
- 软考战损修复：p=0.9, b=10, f*=0.89
- 深度复盘：p=0.9, b=20, f*=0.895
- 资产配置系统：p=0.9, b=20, f*=0.895

**场景二：低赔率做空/休整（b < 1）**
适用：收益难以覆盖成本，存在清零风险。如漫无目的的复习、超线性发展期感情投入、考研二战三战。
即使胜率不低，f*仍可能为负数。最优策略是主动撤出筹码。
历史锚点：
- 漫无目的复习：p=0.15, b=0.4, f*=-1.975
- 考研二战：p=0.65, b=0.5, f*=-0.05

**场景三：优势积累与动态反馈**
适用：初始胜率不高，但可通过执行过程中的"期权收益"动态提升。如职业路径选择。
决策价值包含执行过程中获得的能力成长。
历史锚点：
- 不考研决策（初始）：p=0.5, b=5, f*≈0.4
- 不考研决策（经历实战后）：p=0.85, b=5, f*=0.82

## 输出格式
你必须严格输出一个JSON对象，不要输出任何其他内容，不要使用Markdown代码块包裹。
直接输出纯JSON，以{开头，以}结尾。
示例：
{
  "p": 0.85,
  "q": 0.15,
  "b": 8.0,
  "f_star": 0.8312,
  "scenario_type": "高赔率重注场景",
  "reasoning": "详细的推理过程，包含参数估算依据和计算步骤"
}


## 历史参考（如果有的话）
系统可能会提供与当前场景相似的历史决策记录。请参考这些记录的参数和校准结果来调整本次估算。
如果历史参考显示用户在此类场景的实际表现持续优于初始预估，可以适当上调胜率p；反之则下调。
如果历史参考为空，则忽略此区块，按常规方式估算。

## 注意事项
- 如果用户描述模糊，请基于最合理的假设估算参数，并在reasoning中说明假设
- 参数必须符合实际逻辑：p∈(0,1)，b>0
- 如果场景明显属于低赔率，不要强行给高b值
"""


def analyze(scenario: str, system_prompt:  Optional[str] = None) -> QuantResult:
    """
    使用DeepSeek进行语义级量化分析。
    如果提供 system_prompt，则使用自定义的分身 Prompt。
    """
        # 在所有分身的 system_prompt 末尾强制追加 JSON 输出格式要求
    json_format_instruction = """
    ## 输出格式（必须严格遵守）
    你必须直接输出一个纯JSON对象，不要使用Markdown代码块（不要用```json```包裹），不要添加任何前缀或后缀文字。
    输出必须以 { 开头，以 } 结尾。
    示例：
    {
    "p": 0.85,
    "q": 0.15,
    "b": 8.0,
    "f_star": 0.8312,
    "scenario_type": "高赔率重注场景",
    "reasoning": "详细的推理过程，包含参数估算依据和计算步骤"
    }

    请立即以纯JSON格式输出，不要输出其他任何内容。
    """
    effective_prompt = (system_prompt if system_prompt else QUANT_SYSTEM_PROMPT) + json_format_instruction
    response_text = chat(
        system_prompt=effective_prompt,
        user_message=scenario,
        temperature=0.3,
        max_tokens=1536
    )

    # 尝试从回复中提取JSON
    try:
        # 清理可能的markdown代码块标记
        clean_text = response_text.strip()

        # 去除 Markdown 代码块标记（支持多种变体）
        if clean_text.startswith("```"):
            # 找到第一个换行符，去掉 ```json 或 ``` 开头
            first_newline = clean_text.find("\n")
            if first_newline != -1:
                clean_text = clean_text[first_newline + 1:]
            # 去掉结尾的 ```
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]
            clean_text = clean_text.strip()

        # 尝试找到 JSON 对象的起止位置
        start_idx = clean_text.find("{")
        end_idx = clean_text.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            clean_text = clean_text[start_idx:end_idx + 1]

        data = json.loads(clean_text)

        return QuantResult(
            p=round(float(data["p"]), 4),
            q=round(float(data["q"]), 4),
            b=round(float(data["b"]), 2),
            f_star=round(float(data["f_star"]), 4),
            scenario_type=str(data["scenario_type"]),
            reasoning=str(data["reasoning"])
        )
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        # 如果AI没有按JSON格式输出，返回一个安全的默认结果
        return QuantResult(
            p=0.5,
            q=0.5,
            b=1.0,
            f_star=0.0,
            scenario_type="通用决策场景（AI解析异常，使用默认参数）",
            reasoning=f"AI原始输出未能正确解析为JSON。\n错误: {str(e)}\n原始输出片段: {response_text[:300]}..."
        )