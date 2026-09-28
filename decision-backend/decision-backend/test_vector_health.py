"""
向量功能健康检查脚本
用法：python test_vector_health.py
"""

import time
from vector_store import get_decision_collection

def check_count():
    collection = get_decision_collection()
    count = collection.count()
    print(f"当前 ChromaDB 中存储的决策记录数：{count}")
    return count

if __name__ == "__main__":
    before = check_count()
    print(f"\n请在前端发送一条慢回路决策（例如：'我该不该周末复习高数'）")
    print("发送后等待 3-5 秒，让后台线程完成向量存储...")
    print("按 Enter 键继续检查...")
    input()

    after = check_count()
    if after > before:
        print(f"✅ 向量存储正常！新增了 {after - before} 条记录。")
    else:
        print("⚠️ 向量存储可能未生效。请检查：")
        print("  1. 后端是否已重启并加载了最新代码？")
        print("  2. chroma_db 文件夹权限是否正常？")
        print("  3. 发送的消息是否为慢回路（快回路不会存储向量）？")