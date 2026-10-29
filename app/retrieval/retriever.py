# app/retrieval/retriever.py
from app.models import RetrievedChunk
from app.retrieval.store import VectorStore


class Retriever:
    def __init__(self, store: VectorStore, embedder, top_k: int, score_threshold: float) -> None:
        self.store = store
        self.embedder = embedder
        self.top_k = top_k
        self.score_threshold = score_threshold

    def retrieve(self, question: str) -> list[RetrievedChunk]:
        if self.store.count() == 0:
            return []
        qvec = self.embedder.embed([question])[0]
        hits = self.store.query(embedding=qvec, top_k=self.top_k)
        out: list[RetrievedChunk] = []
        for _id, doc, meta, dist in hits:
            score = 1.0 - dist  # chroma 默认余弦距离 → 相似度
            if score < self.score_threshold:
                continue
            out.append(RetrievedChunk(
                doc_id=meta["doc_id"], source=meta["source"],
                chunk_index=meta["chunk_index"], text=doc, score=round(score, 4),
            ))
        return out
