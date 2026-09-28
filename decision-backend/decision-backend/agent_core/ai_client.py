#agent_core/ai_client.py
"""
DeepSeek API 统一调用模块

所有Agent共享同一个API Key和Client实例。
Agent之间的区分靠不同的System Prompt，而非不同的API Key。
"""
from __future__ import annotations

import os
from openai import OpenAI
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

# 全局单例 Client，所有 Agent 共用
_client: OpenAI | None = None


def get_client() -> OpenAI:
    """获取 DeepSeek API Client 实例（懒加载单例）"""
    global _client
    if _client is None:
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError(
                "未找到 DEEPSEEK_API_KEY。\n"
                "请确保项目根目录下有 .env 文件，且其中包含：\n"
                "DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
            )
        _client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )
    return _client


def chat(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.3,
    max_tokens: int = 1024
) -> str:
    """
    发送单次对话请求到 DeepSeek API。

    参数:
        system_prompt: 系统提示词（定义Agent角色和行为）
        user_message: 用户输入的决策场景描述
        temperature: 随机性参数（0.0=确定性输出，1.0=最大随机性）
        max_tokens: 最大输出长度

    返回:
        str: AI 的回复文本
    """
    client = get_client()
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        temperature=temperature,
        max_tokens=max_tokens
    )
    content = response.choices[0].message.content
    if content is None:
        raise ValueError("DeepSeek API 返回了空内容")
    return content