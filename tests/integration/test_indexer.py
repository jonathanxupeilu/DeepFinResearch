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
    idx.index_document(Document(source="a.md", content="全新版本内容，完全不一样"))
    assert idx.store.list_documents() == ["a.md"]
    assert idx.store.get_by_source("a.md") != ""


def test_index_empty_document_skipped(tmp_path: Path):
    idx = make_indexer(tmp_path)
    r = idx.index_document(Document(source="empty.md", content="   \n  "))
    assert r.skipped and idx.store.count() == 0
