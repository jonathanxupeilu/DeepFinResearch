# tests/integration/test_retriever.py
from pathlib import Path
from unittest.mock import MagicMock

from app.retrieval.retriever import Retriever
from app.retrieval.store import VectorStore


def make_retriever(tmp_path: Path):
    store = VectorStore(persist_dir=tmp_path / "chroma", collection="test")
    embedder = MagicMock()
    embedder.embed.return_value = [[1.0, 0.0]]  # 查询向量固定
    store.upsert(ids=["c1", "c2"],
                 embeddings=[[1.0, 0.0], [0.0, 1.0]],
                 documents=["相关内容", "无关内容"],
                 metadatas=[{"doc_id": "d1", "source": "a.md", "chunk_index": 0},
                            {"doc_id": "d2", "source": "b.md", "chunk_index": 0}])
    return Retriever(store=store, embedder=embedder, top_k=2, score_threshold=0.5)


def test_retrieve_returns_sorted_chunks(tmp_path: Path):
    r = make_retriever(tmp_path)
    hits = r.retrieve("相关问题")
    assert hits[0].text == "相关内容"  # 余弦距离 0 < 1
    assert all(h.score >= 0.5 for h in hits)


def test_retrieve_filters_below_threshold(tmp_path: Path):
    r = make_retriever(tmp_path)
    hits = r.retrieve("相关问题")
    assert len(hits) == 1  # "无关内容" 距离 1.0 → score 0.0 被过滤


def test_retrieve_empty_store(tmp_path: Path):
    store = VectorStore(persist_dir=tmp_path / "chroma2", collection="test")
    embedder = MagicMock()
    embedder.embed.return_value = [[1.0]]
    r = Retriever(store=store, embedder=embedder, top_k=2, score_threshold=0.5)
    assert r.retrieve("任意") == []
