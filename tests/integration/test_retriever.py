# tests/integration/test_retriever.py
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.retrieval.retriever import Retriever
from app.retrieval.store import VectorStore

METADATAS = [
    {"doc_id": "d1", "source": "a.md", "chunk_index": 0},
    {"doc_id": "d2", "source": "b.md", "chunk_index": 0},
]


def make_retriever(tmp_path: Path, score_threshold: float = 0.5):
    store = VectorStore(persist_dir=tmp_path / "chroma", collection="test")
    embedder = MagicMock()
    embedder.embed.return_value = [[1.0, 0.0]]  # 查询向量固定
    store.upsert(
        ids=["c1", "c2"],
        embeddings=[[1.0, 0.0], [0.0, 1.0]],
        documents=["相关内容", "无关内容"],
        metadatas=METADATAS,
    )
    return Retriever(
        store=store, embedder=embedder, top_k=2, score_threshold=score_threshold
    )


def test_retrieve_returns_sorted_chunks(tmp_path: Path):
    r = make_retriever(tmp_path, score_threshold=-1.0)  # 阈值放开，专测排序
    hits = r.retrieve("相关问题")
    assert len(hits) == 2
    # cosine 空间验证：[1,0] 与 [0,1] 余弦距离 1.0 → score ≈ 0.0；若误用 l2 则为负值
    assert hits[1].score == pytest.approx(0.0, abs=1e-3)
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)  # 严格非升序


def test_retrieve_filters_below_threshold(tmp_path: Path):
    r = make_retriever(tmp_path)
    hits = r.retrieve("相关问题")
    assert len(hits) == 1  # "无关内容" 距离 1.0 → score 0.0 被过滤


def test_retrieve_keeps_score_equal_to_threshold(tmp_path: Path):
    # 查询 [1,0] 与 chunk c1 完全相同 → 余弦距离 0.0 → score 恰为 1.0 == threshold
    r = make_retriever(tmp_path, score_threshold=1.0)
    hits = r.retrieve("相关问题")
    assert len(hits) == 1
    assert (
        hits[0].score == 1.0
    )  # score == threshold 时保留（实现为 score < threshold 才过滤）


def test_retrieve_empty_store(tmp_path: Path):
    store = VectorStore(persist_dir=tmp_path / "chroma2", collection="test")
    embedder = MagicMock()
    embedder.embed.return_value = [[1.0]]
    r = Retriever(store=store, embedder=embedder, top_k=2, score_threshold=0.5)
    assert r.retrieve("任意") == []
