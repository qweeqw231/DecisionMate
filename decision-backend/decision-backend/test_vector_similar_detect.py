#test_vector_similar_detect.py
from vector_store import store_decision_vector, search_similar_decisions

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
    print(f"decision_id={r['decision_id']}, similarity={r['similarity']}")  # 如果输出 1，且相似度 >0.7，说明语义检索有效