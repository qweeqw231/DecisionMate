#test_vector.py
r"""
手动向量检索检查脚本（非自动化测试）

警告：本脚本会向**真实** chroma_db 写入一条固定 ID 的向量（decision_id=999），
且该 ID 在 SQLite 中没有对应决策记录 —— 写入后即为孤儿向量。
它原先在导入时直接执行，被 pytest 之类工具收集时会静默污染真实向量库
（实测曾在向量库中留下 id=999/1000 两条孤儿）。

因此现在改为仅在显式运行时才执行主体逻辑：

    .venv\Scripts\python.exe test_vector.py           # 用真实向量库
    $env:CHROMA_DB_PATH=".tmp_chroma"; python test_vector.py   # 或指向隔离目录

清理孤儿请用：python tools\clean_orphan_vectors.py --apply
"""
import os
import traceback


def main() -> None:
    from vector_store import store_decision_vector, search_similar_decisions

    # 1. 测试存储
    print('=== 测试向量存储 ===')
    print(f'[提示] 目标向量库：{os.getenv("CHROMA_DB_PATH", "chroma_db（真实库）")}')
    try:
        store_decision_vector(
            decision_id=999,
            scenario='测试场景：周末应该复习高数还是准备英语考试',
            metadata={'p': 0.7, 'q': 0.3, 'b': 2.0, 'f_star': 0.55, 'scenario_type': '测试', 'conv_id': 1}
        )
        print('向量存储成功（已写入 id=999，测完请用 tools\\clean_orphan_vectors.py 清理）')
    except Exception:
        traceback.print_exc()

    # 2. 测试检索
    print('=== 测试向量检索 ===')
    try:
        results = search_similar_decisions('测试场景：周末应该复习高数还是准备英语考试', top_k=3, threshold=0.5)
        print(f'检索到 {len(results)} 条相似记录')
        for r in results:
            print(f"  decision_id={r['decision_id']}, similarity={r['similarity']}")
    except Exception:
        traceback.print_exc()

    results = search_similar_decisions('我在想要不要用周末两天时间集中攻克软考，因为模考暴露了案例分析部分的漏洞，下周还有数据库考试', top_k=3, threshold=0.5)
    print(f'检索到 {len(results)} 条记录')
    for r in results:
        print(f'  decision_id={r["decision_id"]}, similarity={r["similarity"]}, scenario={r.get("metadata", {}).get("scenario_type", "?")}')


if __name__ == "__main__":
    main()
