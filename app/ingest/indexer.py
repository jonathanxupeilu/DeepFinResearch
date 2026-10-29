import logging

from pydantic import BaseModel

from app.ingest.splitter import TextSplitter
from app.models import Document
from app.retrieval.store import VectorStore

logger = logging.getLogger(__name__)


class IndexResult(BaseModel):
    source: str
    added: int = 0
    skipped: bool = False


class Indexer:
    def __init__(
        self, store: VectorStore, embedder, chunk_size: int, chunk_overlap: int
    ) -> None:
        self.store = store
        self.embedder = embedder
        self.splitter = TextSplitter(chunk_size, chunk_overlap)

    def index_document(self, doc: Document) -> IndexResult:
        existing_doc_id = self.store.get_by_source(doc.source)
        if existing_doc_id == doc.doc_id:  # 内容 hash 相同 → 跳过
            return IndexResult(source=doc.source, skipped=True)
        if existing_doc_id is not None:  # 文档更新 → 删旧切片
            self.store.delete_document_by_source(doc.source)

        texts = self.splitter.split(doc.content)
        if not texts:
            return IndexResult(source=doc.source, skipped=True)
        vectors = self.embedder.embed(texts)
        ids, metas = [], []
        for i, text in enumerate(texts):
            # id 中加入 source，避免不同 source 内容 hash 相同时互相覆盖
            ids.append(f"{doc.source}-{doc.doc_id}-{i}")
            metas.append({"doc_id": doc.doc_id, "source": doc.source, "chunk_index": i})
        self.store.upsert(ids=ids, embeddings=vectors, documents=texts, metadatas=metas)
        logger.info("入库 %s: %d 个切片", doc.source, len(texts))
        return IndexResult(source=doc.source, added=len(texts))
