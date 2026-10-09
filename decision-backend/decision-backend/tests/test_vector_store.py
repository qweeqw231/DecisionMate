# -*- coding: utf-8 -*-
"""向量层测试（P0-4 降级、P0-5 孤儿清理）"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import support  # noqa: F401

import vector_store  # noqa: E402


class _CountingCollection:
    """最小可用的 Chroma 集合替身，忠实支持 get(ids=...) / delete(ids=...)。"""

    def __init__(self, n=5, ids=("1", "2")):
        self._n = n
        self.ids = list(ids)
        self.deleted = []
        self.raise_on_query = False
        self.raise_on_get = False
        self.raise_on_delete = False

    def count(self):
        return self._n

    def query(self, **kwargs):
        if self.raise_on_query:
            raise RuntimeError("Chroma 查询失败")
        return {"ids": [["1"]], "distances": [[0.1]], "metadatas": [[{"p": 0.9}]]}

    def get(self, ids=None, include=None):
        if self.raise_on_get:
            raise RuntimeError("读取失败")
        if ids is None:
            return {"ids": list(self.ids)}
        return {"ids": [i for i in ids if i in self.ids]}

    def delete(self, ids):
        if self.raise_on_delete:
            raise RuntimeError("删除失败")
        self.deleted.extend(ids)
        self.ids = [i for i in self.ids if i not in ids]


class VectorHarness:
    def __init__(self, collection):
        self.collection = collection

    def __enter__(self):
        self._orig_collection = vector_store.get_decision_collection
        self._orig_embed = vector_store.embed_text
        vector_store.get_decision_collection = lambda: self.collection
        return self

    def __exit__(self, *exc):
        vector_store.get_decision_collection = self._orig_collection
        vector_store.embed_text = self._orig_embed
        return False


class TestSearchDegradation(unittest.TestCase):
    """P0-4：检索只是增强项，任何失败都必须降级为空结果而不是中断决策。"""

    def test_embedding_failure_returns_empty(self):
        def boom(text):
            raise RuntimeError("SiliconFlow 不可用")
        with VectorHarness(_CountingCollection()) as _:
            vector_store.embed_text = boom
            self.assertEqual(vector_store.search_similar_decisions("场景"), [])

    def test_query_failure_returns_empty(self):
        collection = _CountingCollection()
        collection.raise_on_query = True
        with VectorHarness(collection):
            vector_store.embed_text = lambda text: [0.0] * 8
            self.assertEqual(vector_store.search_similar_decisions("场景"), [])

    def test_collection_failure_returns_empty(self):
        def boom():
            raise RuntimeError("Chroma 无法打开")
        with VectorHarness(_CountingCollection()):
            vector_store.get_decision_collection = boom
            self.assertEqual(vector_store.search_similar_decisions("场景"), [])

    def test_empty_collection_short_circuits(self):
        with VectorHarness(_CountingCollection(n=0)):
            vector_store.embed_text = lambda text: (_ for _ in ()).throw(
                AssertionError("空集合不应调用 Embedding API"))
            self.assertEqual(vector_store.search_similar_decisions("场景"), [])


class TestDeleteDecisions(unittest.TestCase):
    """P0-5：删除向量是清理孤儿的关键路径。"""

    def test_deletes_matching_ids(self):
        collection = _CountingCollection(ids=("7", "8", "9"))
        with VectorHarness(collection):
            removed = vector_store.delete_decision_vectors([7, 8, 9])
        self.assertEqual(removed, 3)
        self.assertEqual(sorted(collection.deleted), ["7", "8", "9"])

    def test_counts_only_ids_that_actually_exist(self):
        """回归：原先无条件返回 len(ids)，日志会谎报清理量。"""
        collection = _CountingCollection(ids=("7",))
        with VectorHarness(collection):
            removed = vector_store.delete_decision_vectors([7, 8, 9])
        self.assertEqual(removed, 1)
        self.assertEqual(collection.deleted, ["7"])

    def test_missing_ids_report_zero(self):
        collection = _CountingCollection(ids=("1",))
        with VectorHarness(collection):
            self.assertEqual(vector_store.delete_decision_vectors([42]), 0)
        self.assertEqual(collection.deleted, [])

    def test_empty_input_is_a_noop(self):
        collection = _CountingCollection()
        with VectorHarness(collection):
            self.assertEqual(vector_store.delete_decision_vectors([]), 0)
        self.assertEqual(collection.deleted, [])

    def test_delete_failure_is_swallowed(self):
        collection = _CountingCollection(ids=("1",))
        collection.raise_on_delete = True
        with VectorHarness(collection):
            self.assertEqual(vector_store.delete_decision_vectors([1]), 0)

    def test_get_all_ids_failure_returns_empty(self):
        collection = _CountingCollection()
        collection.raise_on_get = True
        with VectorHarness(collection):
            self.assertEqual(vector_store.get_all_decision_vector_ids(), [])


class TestPurgeWiring(unittest.TestCase):
    """删除对话/清空数据时必须调用向量清理。"""

    def test_purge_calls_through(self):
        import main
        captured = []
        original = main.delete_decision_vectors
        main.delete_decision_vectors = lambda ids: (captured.extend(ids), len(ids))[1]
        try:
            removed = main._purge_decision_vectors([1, 2, 3])
        finally:
            main.delete_decision_vectors = original
        self.assertEqual(removed, 3)
        self.assertEqual(captured, [1, 2, 3])

    def test_purge_is_noop_for_empty_input(self):
        import main
        self.assertEqual(main._purge_decision_vectors([]), 0)

    def test_purge_never_raises(self):
        import main
        original = main.delete_decision_vectors

        def boom(ids):
            raise RuntimeError("向量库炸了")
        main.delete_decision_vectors = boom
        try:
            self.assertEqual(main._purge_decision_vectors([1]), 0)
        finally:
            main.delete_decision_vectors = original


if __name__ == "__main__":
    unittest.main()
