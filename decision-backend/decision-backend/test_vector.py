#test_vector.py
from vector_store import store_decision_vector, search_similar_decisions
import traceback

# 1. 测试存储
print('=== 测试向量存储 ===')
try:
    store_decision_vector(
        decision_id=999,
        scenario='测试场景：周末应该复习高数还是准备英语考试',
        metadata={'p': 0.7, 'q': 0.3, 'b': 2.0, 'f_star': 0.55, 'scenario_type': '测试', 'conv_id': 1}
    )
    print('向量存储成功')
except Exception as e:
    traceback.print_exc()

# 2. 测试检索
print('=== 测试向量检索 ===')
try:
    results = search_similar_decisions('测试场景：周末应该复习高数还是准备英语考试', top_k=3, threshold=0.5)
    print(f'检索到 {len(results)} 条相似记录')
    for r in results:
        print(f"  decision_id={r['decision_id']}, similarity={r['similarity']}")
except Exception as e:
    traceback.print_exc()

results = search_similar_decisions('我在想要不要用周末两天时间集中攻克软考，因为模考暴露了案例分析部分的漏洞，下周还有数据库考试', top_k=3, threshold=0.5)
print(f'检索到 {len(results)} 条记录')
for r in results:
    print(f'  decision_id={r["decision_id"]}, similarity={r["similarity"]}, scenario={r.get("metadata", {}).get("scenario_type", "?")}')