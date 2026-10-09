#test_vector_similar_detect.py
r"""
手动语义检索检查脚本（非自动化测试）

警告：本脚本会向**真实** chroma_db 写入一条固定 ID 的向量（decision_id=1000），
该 ID 在 SQLite 中没有对应决策记录 —— 写入后即为孤儿向量。
为避免被 pytest 等工具在导入时静默执行、污染真实向量库，主体逻辑已移入 main()。

    .venv\Scripts\python.exe test_vector_similar_detect.py
    $env:CHROMA_DB_PATH=".tmp_chroma"; python test_vector_similar_detect.py   # 隔离目录

清理孤儿请用：python tools\clean_orphan_vectors.py --apply
"""
import os


def main() -> None:
    from vector_store import store_decision_vector, search_similar_decisions

    print(f'[提示] 目标向量库：{os.getenv("CHROMA_DB_PATH", "chroma_db（真实库）")}')

    # 存储一个决策
    store_decision_vector(
        decision_id=1000,
        scenario="我该不该在考试前夜通宵复习？",
        metadata={"p": 0.2, "b": 0.5}
    )

    # 用语义相似但字面不同的描述查询
    results = search_similar_decisions(
        "考前熬夜看书值得吗？",
        top_k=3,
        threshold=0.5
    )

    print(f"检索到 {len(results)} 条记录")
    for r in results:
        print(f"decision_id={r['decision_id']}, similarity={r['similarity']}")  # 相似度 >0.7 说明语义检索有效


if __name__ == "__main__":
    main()
