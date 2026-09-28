#vector_store.py
"""
向量存储模块
使用 ChromaDB 存储决策的语义指纹，支持相似度检索。
嵌入模型使用 DeepSeek Embedding API。
"""
from __future__ import annotations

import os
import chromadb
from chromadb.config import Settings
from openai import OpenAI
from dotenv import load_dotenv
from typing import Any

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
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")
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
    """检索与当前场景最相似的历史决策"""
    collection = get_decision_collection()
    if collection.count() == 0:
        return []

    query_embedding = embed_text(scenario)
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(top_k, collection.count())
    )

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
    """新增一个能力因子（需用户确认）"""
    from datetime import datetime
    now = datetime.now().isoformat()
    updates = {
        factor_name: value,
        f"{factor_name}_updated_at": now,
        f"{factor_name}_basis": basis
    }
    update_user_profile(updates)