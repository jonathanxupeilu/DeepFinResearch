# app/retrieval/store.py
from pathlib import Path

import chromadb


class VectorStore:
    def __init__(self, persist_dir: Path, collection: str = "knowledge") -> None:
        self.client = chromadb.PersistentClient(path=str(persist_dir))
        self.collection = self.client.get_or_create_collection(collection)

    def upsert(self, ids, embeddings, documents, metadatas) -> None:
        self.collection.upsert(ids=ids, embeddings=embeddings,
                               documents=documents, metadatas=metadatas)

    def query(self, embedding: list[float], top_k: int = 5):
        res = self.collection.query(query_embeddings=[embedding], n_results=top_k)
        return list(zip(res["ids"][0], res["documents"][0],
                        res["metadatas"][0], res["distances"][0]))

    def delete_document(self, doc_id: str) -> None:
        self.collection.delete(where={"doc_id": doc_id})

    def delete_document_by_source(self, source: str) -> None:
        self.collection.delete(where={"source": source})

    def count(self) -> int:
        return self.collection.count()

    def list_documents(self) -> list[str]:
        got = self.collection.get()
        return sorted({m["source"] for m in got["metadatas"]})

    def get_by_source(self, source: str) -> str | None:
        got = self.collection.get(where={"source": source}, include=["metadatas"])
        if not got["metadatas"]:
            return None
        return got["metadatas"][0]["doc_id"]
