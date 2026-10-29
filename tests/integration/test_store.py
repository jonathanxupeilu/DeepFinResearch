# tests/integration/test_store.py
from pathlib import Path

from app.retrieval.store import VectorStore

META = [{"doc_id": "d1", "source": "a.md", "chunk_index": 0},
        {"doc_id": "d1", "source": "a.md", "chunk_index": 1}]


def make_store(tmp_path: Path) -> VectorStore:
    return VectorStore(persist_dir=tmp_path / "chroma", collection="test")


def test_upsert_and_count(tmp_path: Path):
    store = make_store(tmp_path)
    store.upsert(ids=["c1", "c2"], embeddings=[[0.1, 0.2], [0.3, 0.4]],
                 documents=["片段一", "片段二"], metadatas=META)
    assert store.count() == 2


def test_query_top_k(tmp_path: Path):
    store = make_store(tmp_path)
    store.upsert(ids=["c1", "c2"], embeddings=[[1.0, 0.0], [0.0, 1.0]],
                 documents=["相关", "无关"],
                 metadatas=[META[0], {"doc_id": "d2", "source": "b.md", "chunk_index": 0}])
    hits = store.query(embedding=[0.9, 0.1], top_k=1)
    assert len(hits) == 1
    id_, doc, meta, dist = hits[0]
    assert doc == "相关"
    assert meta["source"] == "a.md"


def test_delete_document(tmp_path: Path):
    store = make_store(tmp_path)
    store.upsert(ids=["c1"], embeddings=[[1.0, 0.0]], documents=["x"], metadatas=[META[0]])
    store.delete_document(doc_id="d1")
    assert store.count() == 0


def test_list_and_get_by_source(tmp_path: Path):
    store = make_store(tmp_path)
    store.upsert(ids=["c1"], embeddings=[[1.0]], documents=["x"], metadatas=[META[0]])
    assert "a.md" in store.list_documents()
    assert store.get_by_source("a.md") == "d1"
    assert store.get_by_source("不存在.md") is None
