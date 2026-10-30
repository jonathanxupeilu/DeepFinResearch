from pathlib import Path
from unittest.mock import MagicMock

from app.ingest.indexer import Indexer
from app.models import Document
from app.retrieval.store import VectorStore


def make_indexer(tmp_path: Path) -> Indexer:
    store = VectorStore(persist_dir=tmp_path / "chroma", collection="indexer")
    embedder = MagicMock()
    embedder.embed.side_effect = lambda texts: [[0.1] * 4 for _ in texts]
    return Indexer(store=store, embedder=embedder, chunk_size=50, chunk_overlap=10)


def test_index_adds_chunks(tmp_path: Path):
    idx = make_indexer(tmp_path)
    doc = Document(source="a.md", content="内容文字。" * 30)
    result = idx.index_document(doc)
    assert result.added > 0
    assert not result.skipped
    assert idx.store.count() == result.added


def test_index_same_content_skipped(tmp_path: Path):
    idx = make_indexer(tmp_path)
    idx.index_document(Document(source="a.md", content="相同内容"))
    r2 = idx.index_document(Document(source="a.md", content="相同内容"))
    assert r2.added == 0 and r2.skipped


def test_reindex_replaces_old_version(tmp_path: Path):
    idx = make_indexer(tmp_path)
    idx.index_document(Document(source="a.md", content="旧版本内容"))
    new_doc = Document(source="a.md", content="全新版本内容，完全不一样")
    result = idx.index_document(new_doc)
    assert idx.store.list_documents() == ["a.md"]
    assert idx.store.get_by_source("a.md") == new_doc.doc_id
    assert idx.store.count() == result.added


def test_same_content_different_sources_both_indexed(tmp_path: Path):
    idx = make_indexer(tmp_path)
    r1 = idx.index_document(Document(source="a.md", content="完全相同的内容"))
    r2 = idx.index_document(Document(source="b.md", content="完全相同的内容"))
    assert not r1.skipped and not r2.skipped
    assert idx.store.count() == r1.added + r2.added
    assert idx.store.list_documents() == ["a.md", "b.md"]
    assert idx.store.get_by_source("a.md") is not None
    assert idx.store.get_by_source("b.md") is not None


def test_index_empty_document_skipped(tmp_path: Path):
    idx = make_indexer(tmp_path)
    r = idx.index_document(Document(source="empty.md", content="   \n  "))
    assert r.skipped and idx.store.count() == 0


def test_metadata_contains_indexed_at(tmp_path: Path):
    # 统计卡片需要入库时间来展示「最新入库」；旧数据无此字段由 stats 层兜底
    idx = make_indexer(tmp_path)
    idx.index_document(Document(source="a.md", content="内容文字。" * 30))
    metas = idx.store.get_all_metadatas()
    assert metas
    assert all("indexed_at" in m for m in metas)
