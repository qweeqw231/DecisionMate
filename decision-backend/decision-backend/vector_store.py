#vector_store.py
"""
向量存储模块
使用 ChromaDB 存储决策的语义指纹，支持相似度检索。
嵌入模型使用 DeepSeek Embedding API。
"""
from __future__ import annotations

import logging
import os
import chromadb
from chromadb.config import Settings
from openai import OpenAI
from dotenv import load_dotenv
from typing import Any

from factor_guard import validate_new_factor

load_dotenv()

# 初始化 DeepSeek 客户端（用于嵌入）
_embedding_client: OpenAI | None = None


def _get_embedding_client() -> OpenAI:
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = OpenAI(
            api_key=os.getenv("SILICONFLOW_API_KEY"),
            base_url="https://api.siliconflow.cn/v1"
        )
    return _embedding_client


# 初始化 ChromaDB 客户端（本地持久化）
# 使用 ChromaDB 的 ClientAPI 类型（PersistentClient 返回的父类型）
_chroma_client: Any = None
_decision_collection: Any = None
_profile_collection: Any = None


def _get_chroma_client() -> Any:
    global _chroma_client
    if _chroma_client is None:
        # 默认 chroma_db；测试实例可通过 CHROMA_DB_PATH 指向隔离目录，避免污染真实向量库
        db_path = os.getenv(
            "CHROMA_DB_PATH",
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")
        )
        _chroma_client = chromadb.PersistentClient(path=db_path, settings=Settings(anonymized_telemetry=False))
    return _chroma_client


def get_decision_collection() -> chromadb.Collection:
    """获取决策记录集合（存储语义指纹）"""
    global _decision_collection
    if _decision_collection is None:
        client = _get_chroma_client()
        _decision_collection = client.get_or_create_collection(
            name="decision_records",
            metadata={"description": "决策记录的语义指纹"}
        )
    return _decision_collection


def get_profile_collection() -> chromadb.Collection:
    """获取用户能力档案集合"""
    global _profile_collection
    if _profile_collection is None:
        client = _get_chroma_client()
        _profile_collection = client.get_or_create_collection(
            name="user_profile",
            metadata={"description": "用户长期能力参数"}
        )
    return _profile_collection


def embed_text(text: str) -> list[float]:
    """将文本转换为向量（调用 BAAI/bge-large-zh-v1.5 Embedding API）"""
    client = _get_embedding_client()
    response = client.embeddings.create(
        model="BAAI/bge-large-zh-v1.5",  # 修正模型名称
        input=text
    )
    return response.data[0].embedding


def store_decision_vector(decision_id: int, scenario: str, metadata: dict):
    """存储一条决策的语义指纹"""
    collection = get_decision_collection()
    embedding = embed_text(scenario)
    collection.add(
        ids=[str(decision_id)],
        embeddings=[embedding],
        metadatas=[metadata]
    )


def search_similar_decisions(scenario: str, top_k: int = 5, threshold: float = 0.7) -> list[dict]:
    """
    检索与当前场景最相似的历史决策。

    P0 修复：历史参考是「锦上添花」的增强项，不是决策的前置条件。
    原先本函数在关键路径（main.py 慢回路）上没有任何异常保护，一旦
    Embedding API（SiliconFlow）不可用或 Chroma 异常，整个决策会直接 500，
    与 Phase 4.2「读取失败时系统正常降级」的要求相反。
    现在检索失败一律降级为空结果并记录告警，由调用方继续完成分析。
    """
    try:
        collection = get_decision_collection()
        if collection.count() == 0:
            return []

        query_embedding = embed_text(scenario)
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, collection.count())
        )
    except Exception as e:  # noqa: BLE001 —— 降级优先，绝不因检索失败中断决策
        logging.warning("[向量检索] 失败，已降级为「无历史参考」：%s", e)
        return []

    similar = []
    if results['ids'] and results['ids'][0]:
        for i, doc_id in enumerate(results['ids'][0]):
            distance = results['distances'][0][i] if results['distances'] else 0
            similarity = 1 - distance  # ChromaDB 默认返回距离，转为相似度
            if similarity >= threshold:
                similar.append({
                    "decision_id": int(doc_id),
                    "similarity": round(similarity, 4),
                    "metadata": results['metadatas'][0][i] if results['metadatas'] else {}
                })
    return similar


def get_all_decision_vector_ids() -> list[str]:
    """列出向量库中全部决策向量 ID（用于孤儿向量巡检）。失败时返回空列表。"""
    try:
        collection = get_decision_collection()
        return list(collection.get(include=[])["ids"])
    except Exception as e:  # noqa: BLE001
        logging.warning("[向量库] 读取向量 ID 列表失败：%s", e)
        return []


def delete_decision_vectors(decision_ids) -> int:
    """
    删除指定决策 ID 对应的向量，返回**实际存在并已删除**的数量。

    P0 修复：原先删除对话/清空数据只清 SQLite，Chroma 中的向量会变成孤儿，
    却仍会被检索出来当作「历史参考」注入 Prompt。
    返回真实删除数（先查后删），避免日志谎报清理量。
    """
    ids = [str(i) for i in decision_ids]
    if not ids:
        return 0
    try:
        collection = get_decision_collection()
        existing = collection.get(ids=ids)["ids"]
        if not existing:
            return 0
        collection.delete(ids=existing)
        return len(existing)
    except Exception as e:  # noqa: BLE001 —— 清理失败不应影响删除操作本身
        logging.warning("[向量库] 删除向量失败（ids=%s）：%s", ids, e)
        return 0


def init_user_profile(initial_values: dict):
    """初始化用户能力档案（首次运行时调用）"""
    collection = get_profile_collection()
    existing = collection.get(ids=["user_default"])
    if not existing['ids']:
        collection.add(
            ids=["user_default"],
            embeddings=[[0.0] * 1024],  # 零向量，不用于检索
            metadatas=[initial_values]
        )


def get_user_profile() -> dict:
    """获取当前用户能力档案"""
    collection = get_profile_collection()
    result = collection.get(ids=["user_default"])
    if result['metadatas']:
        return dict(result['metadatas'][0])
    return {}


def update_user_profile(updates: dict):
    """更新用户能力档案的部分字段"""
    collection = get_profile_collection()
    current = get_user_profile()
    current.update(updates)
    collection.update(
        ids=["user_default"],
        metadatas=[current]
    )


def add_profile_factor(factor_name: str, value: float, basis: str):
    """
    新增一个能力因子（需用户在复盘摘要卡片中确认）。

    P0 修复：校验名称与取值范围，避免写入 NaN、越界值或与内部字段冲突的键名。
    """
    from datetime import datetime

    name, safe_value = validate_new_factor(factor_name, value)
    now = datetime.now().isoformat()
    updates = {
        name: safe_value,
        f"{name}_updated_at": now,
        f"{name}_basis": basis
    }
    update_user_profile(updates)
    return name, safe_value